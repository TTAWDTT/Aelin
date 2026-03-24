from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.schemas import AelinChatRequest, AelinChatResponse, AelinToolStep
import app.services.aelin.core as _core
from app.services.aelin.core import _try_agent_loop_chat
from app.services.aelin.core_support import (
    _build_context_bundle,
    _build_cached_base_context_bundle,
    _empty_memory_snapshot,
    _get_memory_summary_for_chat,
    _scoped_web_search_service,
)
from app.services.aelin.expressions import (
    _AELIN_EXPRESSION_IDS,
    _extract_expression_tag,
    _pick_expression,
)
from app.services.aelin.streaming import _now_ms
from app.services.web.web_search import WebSearchService


router = _core.router

_web_search: WebSearchService = _scoped_web_search_service()

def _dispatch_aelin_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> AelinChatResponse:
    return _core._dispatch_aelin_chat(payload, db, current_user, event_cb=event_cb, cancel_token=cancel_token)

