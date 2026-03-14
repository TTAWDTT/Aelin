from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.schemas import AelinChatRequest, AelinChatResponse
import app.services.aelin_core as _core


# Re-export all legacy symbols for compatibility (tests and other modules).
for _name in dir(_core):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_core, _name)


_ORIG_DISPATCH = _core._dispatch_aelin_chat


_SYNC_SYMBOLS = [
    "_resolve_llm_service",
    "_build_context_bundle",
    "_build_cached_base_context_bundle",
    "_build_cached_memory_snapshot",
    "_build_intent_contract",
    "_plan_tool_usage",
    "_critic_tool_plan",
    "_apply_plan_patch",
    "_main_agent_route",
    "_aelin_chat_impl",
    "_try_agent_loop_chat",
    "_start_agent_loop_shadow",
    "_should_use_agent_loop",
    "_should_use_agent_loop_shadow",
    "_file_memory",
    "_memory",
    "_web_search",
    "_media_ingest",
    "_build_media_ingest_answer",
    "_normalize_search_mode",
    "_pick_expression",
    "_now_ms",
]


def _sync_core_runtime() -> dict[str, Any]:
    previous: dict[str, Any] = {}
    for name in _SYNC_SYMBOLS:
        if name in globals():
            previous[name] = getattr(_core, name, None)
            setattr(_core, name, globals()[name])
    return previous


def _restore_core_runtime(previous: dict[str, Any]) -> None:
    for name, value in previous.items():
        setattr(_core, name, value)


def _dispatch_aelin_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> AelinChatResponse:
    previous = _sync_core_runtime()
    try:
        return _ORIG_DISPATCH(payload, db, current_user, event_cb=event_cb, cancel_token=cancel_token)
    finally:
        _restore_core_runtime(previous)
