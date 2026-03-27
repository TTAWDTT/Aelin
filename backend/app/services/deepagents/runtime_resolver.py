from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.db import create_session
from app.services.aelin.core_support import (
    _get_agents_memory_text_for_chat,
    _scoped_web_search_service,
)
from app.services.aelin.runtime import (
    normalize_workspace,
    resolve_llm_service_for_user_id,
)
from app.services.aelin.utils import normalize_positive_ints
from app.services.deepagents.tool_runtime import (
    ToolCallLimiter,
    ToolRuntimeContext,
    build_tool_runtime_context,
)
from app.services.foundation.llm import LLMService
from app.settings import settings


@dataclass
class ResolvedDeepAgentsRuntime:
    user_id: int
    workspace: str
    attachment_ids: list[int]
    service: LLMService
    provider: str
    memory_text: str
    tool_context: ToolRuntimeContext
    limiter: ToolCallLimiter


def normalize_attachment_ids(raw_attachment_ids: object) -> list[int]:
    return normalize_positive_ints(raw_attachment_ids, cap=20)


def build_tool_call_limiter(*, allow_write_tools: bool | None = None) -> ToolCallLimiter:
    allow_writes = (
        bool(getattr(settings, "deepagents_allow_write_tools", False))
        if allow_write_tools is None
        else bool(allow_write_tools)
    )
    return ToolCallLimiter(
        max_tool_calls=int(getattr(settings, "deepagents_max_tool_calls", 512) or 512),
        max_write_calls=int(getattr(settings, "deepagents_max_write_calls", 128) or 128),
        allow_write_tools=allow_writes,
        consecutive_failures_limit=int(
            getattr(settings, "deepagents_consecutive_failures_limit", 3) or 3
        ),
        consecutive_no_progress_limit=int(
            getattr(settings, "deepagents_consecutive_no_progress_limit", 2) or 2
        ),
    )


def resolve_deepagents_runtime(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    raw_attachment_ids: object = None,
    cancel_checker: Callable[[], bool] | None = None,
    session_factory: Callable[[], Session] | None = None,
    allow_write_tools: bool | None = None,
) -> ResolvedDeepAgentsRuntime:
    workspace_norm = normalize_workspace(workspace)
    attachment_ids = normalize_attachment_ids(raw_attachment_ids)
    service, provider = resolve_llm_service_for_user_id(db, int(user_id))
    memory_text = _get_agents_memory_text_for_chat(
        db,
        int(user_id),
        workspace=workspace_norm,
    )
    tool_context = build_tool_runtime_context(
        user_id=int(user_id),
        workspace=workspace_norm,
        web_search_service=_scoped_web_search_service(
            getattr(service.config, "web_search_proxy_url", ""),
        ),
        available_attachment_ids=attachment_ids,
        cancel_checker=cancel_checker,
        session_factory=session_factory or create_session,
    )
    limiter = build_tool_call_limiter(allow_write_tools=allow_write_tools)
    return ResolvedDeepAgentsRuntime(
        user_id=int(user_id),
        workspace=workspace_norm,
        attachment_ids=attachment_ids,
        service=service,
        provider=provider,
        memory_text=memory_text,
        tool_context=tool_context,
        limiter=limiter,
    )
