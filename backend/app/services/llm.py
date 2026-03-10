from __future__ import annotations

import logging
import threading
from typing import Iterator, Any
from urllib.parse import urlparse, urlunparse

import openai
from app.schemas import AgentConfigOut
from app.settings import settings

_log = logging.getLogger(__name__)
_CLIENT_CACHE_LOCK = threading.Lock()
_CLIENT_CACHE: dict[tuple[str, str, str, float], openai.Client] = {}


class LLMService:
    def __init__(self, config: AgentConfigOut, api_key: str | None = None):
        self.config = config
        self.api_key = api_key
        self._client: openai.Client | None = None
        self._client_init_attempted = False
        self.timeout_seconds = max(5.0, float(getattr(settings, "llm_request_timeout_seconds", 90.0)))

    def _setup_client(self) -> None:
        if self._client_init_attempted:
            return
        self._client_init_attempted = True
        if self.config.provider != "rule_based" and self.api_key:
            try:
                normalized_base_url = self._normalize_base_url(self.config.base_url)
                cache_key = (
                    str(self.config.provider or "").strip().lower(),
                    normalized_base_url,
                    str(self.api_key or ""),
                    float(self.timeout_seconds),
                )
                with _CLIENT_CACHE_LOCK:
                    cached = _CLIENT_CACHE.get(cache_key)
                    if cached is None:
                        cached = openai.Client(
                            base_url=normalized_base_url,
                            api_key=self.api_key,
                            timeout=self.timeout_seconds,
                            max_retries=1,
                        )
                        _CLIENT_CACHE[cache_key] = cached
                self._client = cached
            except Exception as e:
                _log.warning("Failed to initialize OpenAI client: %s", e)

    @property
    def client(self) -> openai.Client | None:
        if self._client is None:
            self._setup_client()
        return self._client

    @client.setter
    def client(self, value: openai.Client | None) -> None:
        self._client = value
        self._client_init_attempted = True

    @staticmethod
    def _normalize_base_url(raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            return text
        try:
            parsed = urlparse(text)
            path = (parsed.path or "").rstrip("/")
            # Many providers document full endpoints; OpenAI client expects API root.
            for suffix in ("/chat/completions", "/completions"):
                if path.endswith(suffix):
                    path = path[: -len(suffix)]
                    break
            normalized = parsed._replace(path=path, params="", query="", fragment="")
            return urlunparse(normalized).rstrip("/")
        except Exception:
            return text.rstrip("/")

    def is_configured(self) -> bool:
        return self.config.provider != "rule_based" and bool(self.api_key)

    def _chat(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 500,
        stream: bool = False,
    ) -> str | Iterator[str]:
        if not self.client:
            raise ValueError("LLM not configured")

        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=max_tokens,
                stream=stream,
            )
            if stream:
                return self._stream_generator(response)
            return response.choices[0].message.content.strip()
        except Exception as e:
            _log.error("LLM Error: %s", e)
            raise ValueError(f"LLM invocation failed: {str(e)}") from e

    def _stream_generator(self, response) -> Iterator[str]:
        try:
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            _log.error("Stream Error: %s", e)
            yield f"\n[Error: {str(e)}]"

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        tool_executor: Any = None,
        *,
        max_rounds: int = 3,
        max_calls_per_round: int = 6,
    ) -> Iterator[str]:
        if not self.client:
            yield "Agent not configured."
            return

        tool_defs = tools if tools else None
        rounds = max(1, min(6, int(max_rounds or 3)))
        per_round = max(1, min(10, int(max_calls_per_round or 6)))

        for round_idx in range(rounds):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=self.config.temperature,
                    stream=False,
                    tools=tool_defs,
                )
            except Exception as e:
                yield f"Error: {str(e)}"
                return

            choice = response.choices[0] if response.choices else None
            if choice is None:
                yield "Error: empty LLM response."
                return

            msg = choice.message
            text_out = (msg.content or "").strip()
            raw_tool_calls = list(msg.tool_calls or [])

            if raw_tool_calls and tool_executor:
                tool_calls_payload: list[dict[str, Any]] = []
                for tc in raw_tool_calls[:per_round]:
                    tc_id = getattr(tc, "id", "") or ""
                    fn = getattr(tc, "function", None)
                    fn_name = getattr(fn, "name", "") if fn is not None else ""
                    fn_args = getattr(fn, "arguments", "{}") if fn is not None else "{}"
                    tool_calls_payload.append(
                        {
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": fn_name,
                                "arguments": fn_args,
                            },
                        }
                    )

                messages.append(
                    {
                        "role": "assistant",
                        "content": text_out or "",
                        "tool_calls": tool_calls_payload,
                    }
                )

                for tc in tool_calls_payload:
                    fn_name = str(tc.get("function", {}).get("name") or "").strip()
                    fn_args = str(tc.get("function", {}).get("arguments") or "{}")
                    result_content = tool_executor.execute(fn_name, fn_args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id") or "",
                            "content": str(result_content),
                        }
                    )
                continue

            # Final answer: keep stream UX by chunking text.
            final_text = text_out or "我已经完成处理，但当前没有可输出的正文。"
            chunk_size = 96
            for i in range(0, len(final_text), chunk_size):
                yield final_text[i : i + chunk_size]
            return

        yield "我尝试调用工具完成请求，但达到最大工具轮次。请缩小问题范围后重试。"

    def summarize(self, text: str, stream: bool = False) -> str | Iterator[str]:
        messages = [
            {
                "role": "system",
                "content": "你是 MercuryDesk 的邮件助手。请用简体中文总结用户提供的内容，保留关键信息，避免冗余。不要自行截断。",
            },
            {"role": "user", "content": text},
        ]
        return self._chat(messages, max_tokens=1000, stream=stream)

    def draft_reply(
        self, text: str, tone: str = "friendly", stream: bool = False
    ) -> str | Iterator[str]:
        tone_zh = "友好" if tone in {"friendly", "casual"} else "正式"
        messages = [
            {
                "role": "system",
                "content": f"你是 MercuryDesk 的邮件助手。请用简体中文生成一封“{tone_zh}”语气的回复草稿，简洁清晰，可直接发送。",
            },
            {"role": "user", "content": text},
        ]
        return self._chat(messages, max_tokens=360, stream=stream)
