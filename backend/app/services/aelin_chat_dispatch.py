from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import User
from app.schemas import AelinChatRequest, AelinChatResponse, AelinToolStep


def start_agent_loop_shadow(
    payload: AelinChatRequest,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    baseline_answer: str = "",
    create_session: Callable[[], Session],
    try_agent_loop_chat: Callable[..., AelinChatResponse | None],
    logger: Any,
    now_ms: Callable[[], int],
) -> None:
    query_preview = str(payload.query or "").strip()[:120]

    def _worker() -> None:
        shadow_db = create_session()
        started = time.perf_counter()
        try:
            shadow_user = shadow_db.get(User, int(current_user.id))
            if shadow_user is None:
                return
            shadow_payload = AelinChatRequest.model_validate(payload.model_dump())
            result = try_agent_loop_chat(
                shadow_payload,
                shadow_db,
                shadow_user,
                event_cb=None,
                persist_memory=False,
                force_disable_writes=True,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if result is None:
                logger.warning("aelin agent_loop shadow failed query=%s latency_ms=%s", query_preview, latency_ms)
                if event_cb is not None:
                    event_cb(
                        "trace",
                        {
                            "step": AelinToolStep(
                                stage="agent_loop_shadow",
                                status="failed",
                                detail=f"query={query_preview}; latency_ms={latency_ms}",
                                count=0,
                                ts=now_ms(),
                            ).model_dump()
                        },
                    )
                return
            answer_preview = str(result.answer or "").strip()[:120]
            baseline_preview = str(baseline_answer or "").strip()[:120]
            logger.info(
                "aelin agent_loop shadow ok query=%s latency_ms=%s baseline_len=%s shadow_len=%s",
                query_preview,
                latency_ms,
                len(baseline_preview),
                len(answer_preview),
            )
            if event_cb is not None:
                event_cb(
                    "trace",
                    {
                        "step": AelinToolStep(
                            stage="agent_loop_shadow",
                            status="completed",
                            detail=f"query={query_preview}; latency_ms={latency_ms}",
                            count=1,
                            ts=now_ms(),
                        ).model_dump()
                    },
                )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("aelin agent_loop shadow exception query=%s latency_ms=%s err=%s", query_preview, latency_ms, str(exc)[:180])
            if event_cb is not None:
                event_cb(
                    "trace",
                    {
                        "step": AelinToolStep(
                            stage="agent_loop_shadow",
                            status="failed",
                            detail=f"query={query_preview}; err={str(exc)[:120]}",
                            count=0,
                            ts=now_ms(),
                        ).model_dump()
                    },
                )
        finally:
            try:
                shadow_db.close()
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True, name="aelin-agent-loop-shadow").start()


def dispatch_aelin_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    should_use_agent_loop: Callable[[User, str], bool],
    detect_forced_tracking_create: Callable[[str], dict[str, str] | None],
    try_agent_loop_chat: Callable[..., AelinChatResponse | None],
    legacy_chat_impl: Callable[..., AelinChatResponse],
    should_use_agent_loop_shadow: Callable[[User, str], bool],
    start_agent_loop_shadow_fn: Callable[..., None],
    hard_fail_enabled: bool,
    pick_expression: Callable[[str, str], str],
    now_ms: Callable[[], int],
) -> AelinChatResponse:
    if should_use_agent_loop(current_user, payload.workspace):
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
        if hard_fail_enabled:
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
                        detail="hard_fail_no_legacy_fallback",
                        count=0,
                        ts=now_ms(),
                    )
                ],
                memory_summary="",
                generated_at=datetime.now(timezone.utc),
            )
    legacy = legacy_chat_impl(payload, db, current_user, event_cb=event_cb)
    if should_use_agent_loop_shadow(current_user, payload.workspace):
        start_agent_loop_shadow_fn(
            payload,
            current_user,
            event_cb=event_cb,
            baseline_answer=str(legacy.answer or "")[:800],
        )
    return legacy
