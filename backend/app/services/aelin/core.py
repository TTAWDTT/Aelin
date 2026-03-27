from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.models import User
from app.schemas import ChatAction, ChatRequest, ChatResponse
from app.services.aelin.core_support import (
    _get_agents_memory_text_for_chat,
    _scoped_web_search_service,
)
from app.services.aelin.expressions import _pick_expression
from app.services.aelin.runtime import (
    normalize_workspace as _normalize_workspace,
    resolve_llm_service as _resolve_llm_service,
)
from app.services.aelin.utils import normalize_positive_ints
from app.services.deepagents.cancel_utils import is_cancelled
from app.services.deepagents.deepagents_graph import run_deepagents_loop
from app.services.deepagents.input_mapping import (
    normalize_history_turns,
    normalize_image_inputs,
)
from app.services.deepagents.tool_runtime import ToolCallLimiter, build_tool_runtime_context
from app.settings import settings

router = APIRouter(prefix="/aelin", tags=["aelin"])
_log = logging.getLogger(__name__)

_base_context_cache_lock = threading.Lock()
_base_context_cache: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}
_NO_RESULT_ANSWER = "当前会话使用 DeepAgents，但本轮未获得可用结果。请稍后重试，或检查模型配置后再试。"


def _normalize_attachment_ids(raw_ids: list[Any]) -> list[int]:
    return normalize_positive_ints(raw_ids, cap=20)


def _map_actions(raw_actions: list[dict[str, Any]]) -> list[ChatAction]:
    actions: list[ChatAction] = []
    for raw in raw_actions[:4]:
        kind = str(raw.get("kind") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not kind or not title:
            continue
        detail = str(raw.get("detail") or "").strip()
        payload = {
            str(key): str(value)
            for key, value in raw.items()
            if str(key) not in {"kind", "title", "detail"} and str(value or "").strip()
        }
        actions.append(
            ChatAction(
                kind=kind[:32],
                title=title[:120],
                detail=detail[:220],
                payload=payload,
            )
        )
    return actions


def _try_deepagents_chat(
    payload: ChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    force_disable_writes: bool = False,
    cancel_token: Any | None = None,
) -> ChatResponse | None:
    del event_cb
    if is_cancelled(cancel_token):
        return None

    preflight_started = time.perf_counter()
    source = str(getattr(payload, "source", "chat_ui") or "chat_ui")[:32]
    workspace = _normalize_workspace(payload.workspace)
    query_preview = " ".join(str(payload.query or "").split())[:120]

    resolve_started = time.perf_counter()
    service, provider = _resolve_llm_service(db, current_user)
    _log.info(
        "deepagents preflight phase=resolve_service user_id=%s source=%s workspace=%s provider=%s latency_ms=%s query=%s",
        int(current_user.id),
        source,
        workspace,
        str(provider or ""),
        int((time.perf_counter() - resolve_started) * 1000),
        query_preview,
    )
    if provider == "rule_based" or not service.is_configured():
        return None

    summary_started = time.perf_counter()
    agents_memory_text = _get_agents_memory_text_for_chat(
        db,
        current_user.id,
        workspace=workspace,
    )
    _log.info(
        "deepagents preflight phase=memory_file user_id=%s source=%s workspace=%s bytes=%s latency_ms=%s",
        int(current_user.id),
        source,
        workspace,
        len(agents_memory_text.encode("utf-8")) if agents_memory_text else 0,
        int((time.perf_counter() - summary_started) * 1000),
    )

    normalize_started = time.perf_counter()
    history_turns = normalize_history_turns(payload.history)
    images = normalize_image_inputs(payload.images)
    attachment_ids = _normalize_attachment_ids(getattr(payload, "attachment_ids", []))
    _log.info(
        "deepagents preflight phase=normalize_inputs user_id=%s source=%s workspace=%s history_turns=%s images=%s latency_ms=%s",
        int(current_user.id),
        source,
        workspace,
        len(history_turns),
        len(images),
        int((time.perf_counter() - normalize_started) * 1000),
    )

    if is_cancelled(cancel_token):
        return None

    tool_runtime_started = time.perf_counter()
    tool_context = build_tool_runtime_context(
        db=db,
        user_id=current_user.id,
        workspace=workspace,
        web_search_service=_scoped_web_search_service(
            getattr(service.config, "web_search_proxy_url", ""),
        ),
        available_attachment_ids=attachment_ids,
    )
    _log.info(
        "deepagents preflight phase=tool_runtime_ready user_id=%s source=%s workspace=%s latency_ms=%s",
        int(current_user.id),
        source,
        workspace,
        int((time.perf_counter() - tool_runtime_started) * 1000),
    )

    limiter = ToolCallLimiter(
        max_tool_calls=int(getattr(settings, "deepagents_max_tool_calls", 512) or 512),
        max_write_calls=int(getattr(settings, "deepagents_max_write_calls", 128) or 128),
        allow_write_tools=(
            False
            if force_disable_writes
            else bool(getattr(settings, "deepagents_allow_write_tools", False))
        ),
    )
    _log.info(
        "deepagents preflight phase=runner_ready user_id=%s source=%s workspace=%s total_preflight_ms=%s",
        int(current_user.id),
        source,
        workspace,
        int((time.perf_counter() - preflight_started) * 1000),
    )

    result = run_deepagents_loop(
        service=service,
        provider=provider,
        context=tool_context,
        limiter=limiter,
        query=payload.query,
        memory_text=agents_memory_text,
        history_turns=history_turns,
        images=images,
        cancel_token=cancel_token,
    )

    if is_cancelled(cancel_token) or bool(result.cancelled):
        return None
    answer = str(result.answer or "").strip()
    if not result.ok or not answer:
        return None

    return ChatResponse(
        answer=answer,
        citations=[],
        actions=_map_actions(result.actions),
        memory_summary=agents_memory_text,
        generated_at=datetime.now(timezone.utc),
    )


def _build_no_result_response(
    payload: ChatRequest,
) -> ChatResponse:
    answer = _NO_RESULT_ANSWER
    return ChatResponse(
        answer=answer,
        expression=_pick_expression(payload.query, answer),
        citations=[],
        actions=[],
        memory_summary="",
        generated_at=datetime.now(timezone.utc),
    )


def is_deepagents_no_result_response(response: ChatResponse | None) -> bool:
    if response is None:
        return False
    answer = str(getattr(response, "answer", "") or "").strip()
    return answer == _NO_RESULT_ANSWER


def run_chat_request(
    payload: ChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> ChatResponse:
    response = _try_deepagents_chat(
        payload,
        db,
        current_user,
        event_cb=event_cb,
        cancel_token=cancel_token,
    )
    if response is not None:
        return response
    return _build_no_result_response(payload)
