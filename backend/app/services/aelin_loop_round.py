from __future__ import annotations

from typing import Any

from app.services.aelin_loop_message import is_multimodal_unsupported_error, strip_images_from_messages
from app.services.aelin_loop_types import AgentLoopTraceStep
from app.services.llm import LLMService


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
        response = client.chat.completions.create(
            model=service.config.model,
            messages=messages,
            temperature=service.config.temperature,
            max_tokens=420,
            tools=tools,
            tool_choice="auto",
            timeout=round_timeout_seconds,
        )
        return response, retried_without_images, ""
    except Exception as exc:
        can_retry_without_images = bool(
            (not retried_without_images)
            and is_multimodal_unsupported_error(exc)
            and strip_images_from_messages(messages)
        )
        if can_retry_without_images:
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
                return response, True, ""
            except Exception as retry_exc:
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

