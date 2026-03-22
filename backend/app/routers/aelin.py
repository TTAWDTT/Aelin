from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.schemas import (
    AelinAction,
    AelinChatRequest,
    AelinChatResponse,
    AelinCitation,
    AelinMemoryLayerItem,
    AelinMemoryLayers,
    AelinToolStep,
    AelinTodoItem,
)
import app.services.aelin.core as _core
from app.services.aelin.core import (  # re-export for tests/legacy callers
    _try_agent_loop_chat,
    _aelin_chat_impl,
)
from app.services.aelin.core_support import (
    _build_context_bundle,
    _build_cached_base_context_bundle,
    _scoped_web_search_service,
    _empty_memory_snapshot,
    _get_memory_summary_for_chat,
)
from app.routers.aelin_text_helpers import (
    _AELIN_EXPRESSION_IDS,
    _apply_answer_emoji,
    _dedupe_citations,
    _expression_mapping_prompt,
    _extract_emoji_tag,
    _extract_expression_tag,
    _now_ms,
    _pick_expression,
)
from app.services.web.web_search import WebSearchService
from app.services.memory.file_memory_bridge import file_memory_bridge as _file_memory
from app.services.memory.agent_memory import AgentMemoryService as _AgentMemoryService


# Re-export the FastAPI router defined in aelin_core so that `app.routers.aelin`
# continues to behave like the legacy router module for main.py and tests.
router = _core.router


# Backwards-compatible symbols expected by tests and legacy callers.
_web_search: WebSearchService = _scoped_web_search_service()
_memory = _AgentMemoryService()

def _dispatch_aelin_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> AelinChatResponse:
    return _core._dispatch_aelin_chat(payload, db, current_user, event_cb=event_cb, cancel_token=cancel_token)

