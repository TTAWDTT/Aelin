from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import User
from app.schemas import AelinChatRequest, AelinChatResponse, AelinToolStep


def dispatch_aelin_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    detect_forced_tracking_create: Callable[[str], dict[str, str] | None],
    try_agent_loop_chat: Callable[..., AelinChatResponse | None],
    pick_expression: Callable[[str, str], str],
    now_ms: Callable[[], int],
) -> AelinChatResponse:
    forced_tracking_create = detect_forced_tracking_create(payload.query)
    agent_response = (
        try_agent_loop_chat(
            payload,
            db,
            current_user,
            event_cb=event_cb,
            forced_tracking_create=forced_tracking_create,
        )
        if forced_tracking_create
        else try_agent_loop_chat(payload, db, current_user, event_cb=event_cb)
    )
    if agent_response is not None:
        return agent_response

    answer = "当前会话仅使用 Agent Loop，但本轮未获得可用结果。请稍后重试，或检查模型配置后再试。"
    return AelinChatResponse(
        answer=answer,
        expression=pick_expression(payload.query, answer),
        citations=[],
        actions=[],
        tool_trace=[
            AelinToolStep(
                stage="agent_loop",
                status="failed",
                detail="agent_loop_no_result",
                count=0,
                ts=now_ms(),
            )
        ],
        memory_summary="",
        generated_at=datetime.now(timezone.utc),
    )
