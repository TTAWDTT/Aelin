from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.services.attachments.attachment_service import (
    AttachmentService,
    get_attachment_service,
)
from app.services.foundation.service_utils import normalize_positive_ints
from app.services.memory.agent_memory import AgentMemoryService, get_agent_memory_service
from app.services.web.web_search import WebSearchService


def normalize_workspace(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


@dataclass
class ToolRuntimeContext:
    user_id: int
    workspace: str
    web_search_service: WebSearchService
    attachment_service: AttachmentService
    memory_service: AgentMemoryService
    available_attachment_ids: list[int]
    cancel_checker: Callable[[], bool] | None = None
    session_factory: Callable[[], Session] | None = None
    run_started_monotonic: float | None = None
    run_budget_seconds: float | None = None
    run_deadline_monotonic: float | None = None


def build_tool_runtime_context(
    *,
    user_id: int,
    workspace: str,
    web_search_service: WebSearchService | None = None,
    attachment_service: AttachmentService | None = None,
    memory_service: AgentMemoryService | None = None,
    available_attachment_ids: list[int] | None = None,
    cancel_checker: Callable[[], bool] | None = None,
    session_factory: Callable[[], Session] | None = None,
    run_started_monotonic: float | None = None,
    run_budget_seconds: float | None = None,
    run_deadline_monotonic: float | None = None,
) -> ToolRuntimeContext:
    return ToolRuntimeContext(
        user_id=int(user_id),
        workspace=normalize_workspace(workspace),
        web_search_service=web_search_service or WebSearchService(),
        attachment_service=attachment_service or get_attachment_service(),
        memory_service=memory_service or get_agent_memory_service(),
        available_attachment_ids=normalize_positive_ints(available_attachment_ids, cap=20),
        cancel_checker=cancel_checker,
        session_factory=session_factory,
        run_started_monotonic=run_started_monotonic,
        run_budget_seconds=run_budget_seconds,
        run_deadline_monotonic=run_deadline_monotonic,
    )
