from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.services.aelin.attachment_service import (
    AelinAttachmentService,
    get_aelin_attachment_service,
)
from app.services.aelin.utils import normalize_positive_ints
from app.services.web.web_search import WebSearchService


def normalize_workspace(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


@dataclass
class ToolRuntimeContext:
    db: Session
    user_id: int
    workspace: str
    web_search_service: WebSearchService
    attachment_service: AelinAttachmentService
    available_attachment_ids: list[int]


def build_tool_runtime_context(
    *,
    db: Session,
    user_id: int,
    workspace: str,
    web_search_service: WebSearchService | None = None,
    attachment_service: AelinAttachmentService | None = None,
    available_attachment_ids: list[int] | None = None,
) -> ToolRuntimeContext:
    return ToolRuntimeContext(
        db=db,
        user_id=int(user_id),
        workspace=normalize_workspace(workspace),
        web_search_service=web_search_service or WebSearchService(),
        attachment_service=attachment_service or get_aelin_attachment_service(),
        available_attachment_ids=normalize_positive_ints(available_attachment_ids, cap=20),
    )


@dataclass
class ToolPolicyDecision:
    allowed: bool
    is_write: bool
    reason: str = ""


@dataclass
class ToolPolicyUsage:
    total_calls: int = 0
    write_calls: int = 0


def classify_tool_call(name: str, args: dict[str, Any]) -> bool:
    tool = str(name or "").strip().lower()
    action = str((args or {}).get("action") or "").strip().lower()

    if tool == "device":
        return action in {"open_url", "open_aelin"}
    if tool in {"web_search", "attachment_search", "screen_get"}:
        return False
    if tool == "google_workspace":
        return action in {"calendar_create_event", "gmail_send", "gmail_draft", "docs_create"}
    return False


def _deny_if_over_limit(
    *,
    current: int,
    limit: int,
    reason: str,
    is_write: bool = False,
) -> ToolPolicyDecision | None:
    if int(current) >= int(limit):
        return ToolPolicyDecision(allowed=False, is_write=is_write, reason=reason)
    return None


class ToolCallLimiter:
    def __init__(
        self,
        *,
        max_tool_calls: int,
        max_write_calls: int,
        allow_write_tools: bool,
    ) -> None:
        self.max_tool_calls = max(1, int(max_tool_calls or 1))
        self.max_write_calls = max(0, int(max_write_calls or 0))
        self.allow_write_tools = bool(allow_write_tools)

    def evaluate(self, *, name: str, args: dict[str, Any], usage: ToolPolicyUsage) -> ToolPolicyDecision:
        tool = str(name or "").strip().lower()
        if tool not in {"device", "web_search", "attachment_search", "screen_get", "google_workspace"}:
            return ToolPolicyDecision(allowed=False, is_write=False, reason="unsupported_tool")

        total_limit_deny = _deny_if_over_limit(
            current=usage.total_calls,
            limit=self.max_tool_calls,
            reason="total_call_limit",
        )
        if total_limit_deny is not None:
            return total_limit_deny

        is_write = classify_tool_call(tool, args)
        if is_write and not self.allow_write_tools:
            return ToolPolicyDecision(allowed=False, is_write=True, reason="write_tools_disabled")
        if is_write:
            write_limit_deny = _deny_if_over_limit(
                current=usage.write_calls,
                limit=self.max_write_calls,
                reason="write_call_limit",
                is_write=True,
            )
            if write_limit_deny is not None:
                return write_limit_deny

        return ToolPolicyDecision(allowed=True, is_write=is_write, reason="ok")
