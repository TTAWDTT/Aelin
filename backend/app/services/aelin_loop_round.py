from __future__ import annotations

import logging
from typing import Any

from app.services.aelin_loop_logging import safe_preview
from app.services.aelin_loop_message import is_multimodal_unsupported_error, strip_images_from_messages
from app.services.aelin_loop_types import AgentLoopTraceStep
from app.services.llm import LLMService

_LOG = logging.getLogger(__name__)


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") != "text":
                continue
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
        return " ".join(parts)
    return ""


def _count_image_parts(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").startswith("image"):
                total += 1
    return total


def _log_llm_response(*, round_index: int, response: Any) -> None:
    choice = response.choices[0] if getattr(response, "choices", None) else None
    message = getattr(choice, "message", None) if choice else None
    text_out = _extract_text_content(getattr(message, "content", ""))
    raw_tool_calls = list(getattr(message, "tool_calls", []) or [])
    tool_names: list[str] = []
    for tc in raw_tool_calls[:6]:
        fn = getattr(tc, "function", None)
        name = str(getattr(fn, "name", "") or "").strip()
        if name:
            tool_names.append(name)
    finish_reason = str(getattr(choice, "finish_reason", "") or "")
    _LOG.info(
        "agent_loop llm_response round=%s finish_reason=%s tool_calls=%s tools=%s text=%s",
        round_index,
        finish_reason or "-",
        len(raw_tool_calls),
        ",".join(tool_names) or "-",
        safe_preview(text_out),
    )


def request_round_response(
    *,
    client: Any,
    service: LLMService,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    round_timeout_seconds: float,
    round_index: int,
    trace_steps: list[AgentLoopTraceStep],
    retried_without_images: bool,
) -> tuple[Any | None, bool, str]:
    try:
        _LOG.info(
            "agent_loop llm_request round=%s messages=%s tools=%s image_parts=%s timeout_s=%.1f",
            round_index,
            len(messages),
            len(tools),
            _count_image_parts(messages),
            float(round_timeout_seconds),
        )
        response = client.chat.completions.create(
            model=service.config.model,
            messages=messages,
            temperature=service.config.temperature,
            max_tokens=420,
            tools=tools,
            tool_choice="auto",
            timeout=round_timeout_seconds,
        )
        _log_llm_response(round_index=round_index, response=response)
        return response, retried_without_images, ""
    except Exception as exc:
        _LOG.warning(
            "agent_loop llm_request_failed round=%s error=%s",
            round_index,
            str(exc)[:200],
        )
        can_retry_without_images = bool(
            (not retried_without_images)
            and is_multimodal_unsupported_error(exc)
            and strip_images_from_messages(messages)
        )
        if can_retry_without_images:
            _LOG.info("agent_loop llm_retry_without_images round=%s", round_index)
            trace_steps.append(
                AgentLoopTraceStep(
                    stage="agent_loop_round",
                    status="running",
                    detail=f"round={round_index}; retry_without_images",
                    count=0,
                )
            )
            try:
                response = client.chat.completions.create(
                    model=service.config.model,
                    messages=messages,
                    temperature=service.config.temperature,
                    max_tokens=420,
                    tools=tools,
                    tool_choice="auto",
                    timeout=round_timeout_seconds,
                )
                _log_llm_response(round_index=round_index, response=response)
                return response, True, ""
            except Exception as retry_exc:
                _LOG.warning(
                    "agent_loop llm_retry_failed round=%s error=%s",
                    round_index,
                    str(retry_exc)[:200],
                )
                trace_steps.append(
                    AgentLoopTraceStep(
                        stage="agent_loop_round",
                        status="failed",
                        detail=f"round={round_index}; llm_error={str(retry_exc)[:160]}",
                        count=0,
                    )
                )
                return None, True, "llm_error"
        trace_steps.append(
            AgentLoopTraceStep(
                stage="agent_loop_round",
                status="failed",
                detail=f"round={round_index}; llm_error={str(exc)[:160]}",
                count=0,
            )
        )
        return None, retried_without_images, "llm_error"
