from __future__ import annotations

import logging
from typing import Iterator, Any
from urllib.parse import urlparse, urlunparse

import openai
from app.schemas import AgentConfigOut
from app.settings import settings

_log = logging.getLogger(__name__)


class LLMService:
    def __init__(self, config: AgentConfigOut, api_key: str | None = None):
        self.config = config
        self.api_key = api_key
        self.client: openai.Client | None = None
        self.timeout_seconds = max(5.0, float(getattr(settings, "llm_request_timeout_seconds", 90.0)))
        self._setup_client()

    def _setup_client(self) -> None:
        if self.config.provider != "rule_based" and self.api_key:
            try:
                normalized_base_url = self._normalize_base_url(self.config.base_url)
                self.client = openai.Client(
                    base_url=normalized_base_url,
                    api_key=self.api_key,
                    timeout=self.timeout_seconds,
                    max_retries=1,
                )
            except Exception as e:
                _log.warning("Failed to initialize OpenAI client: %s", e)

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
        return self.client is not None

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
