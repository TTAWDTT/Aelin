from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.services.foundation.service_utils import normalize_positive_ints


@dataclass
class ToolPolicyDecision:
    allowed: bool
    is_write: bool
    reason: str = ""


@dataclass
class ToolPolicyUsage:
    total_calls: int = 0
    write_calls: int = 0
    consecutive_failures: int = 0
    consecutive_no_progress: int = 0
    tool_counts: dict[str, int] = field(default_factory=dict)
    signature_counts: dict[str, int] = field(default_factory=dict)

    def note_invocation(self, name: str, args: dict[str, Any]) -> str:
        tool = str(name or "").strip().lower()
        signature = build_tool_signature(tool, args)
        self.tool_counts[tool] = self.tool_counts.get(tool, 0) + 1
        self.signature_counts[signature] = self.signature_counts.get(signature, 0) + 1
        return signature

    def note_denial(self) -> None:
        self.consecutive_failures += 1
        self.consecutive_no_progress += 1

    def note_result(self, result: dict[str, Any]) -> None:
        is_ok = bool(result.get("ok"))
        has_progress = result_has_progress(result)
        if is_ok:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

        if has_progress:
            self.consecutive_no_progress = 0
        else:
            self.consecutive_no_progress += 1


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = parsed.query
    if scheme not in {"http", "https"} or not netloc:
        return text.lower()
    normalized = f"{scheme}://{netloc}{path}"
    if query:
        normalized = f"{normalized}?{query}"
    return normalized


def _normalize_attachment_ids(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return sorted(normalize_positive_ints(value, cap=20))


def _normalize_memory_kinds(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    normalized = [_normalize_text(item) for item in raw_items]
    return sorted(item for item in normalized if item)


def _normalize_filepaths(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = [" ".join(str(item or "").strip().split()) for item in value]
    return [item[:512] for item in items if item]


def build_tool_signature(name: str, args: dict[str, Any]) -> str:
    tool = str(name or "").strip().lower()
    action = _normalize_text((args or {}).get("action"))
    if tool == "web_search":
        return json.dumps(
            {
                "tool": tool,
                "action": action or "search_and_fetch",
                "query": _normalize_text((args or {}).get("query")),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    if tool == "attachment_search":
        return json.dumps(
            {
                "tool": tool,
                "query": _normalize_text((args or {}).get("query")),
                "attachment_ids": _normalize_attachment_ids((args or {}).get("attachment_ids")),
                "mode": _normalize_text((args or {}).get("mode")) or "keyword",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    if tool == "memory_search":
        return json.dumps(
            {
                "tool": tool,
                "query": _normalize_text((args or {}).get("query")),
                "kinds": _normalize_memory_kinds((args or {}).get("kinds")),
                "top_k": int((args or {}).get("top_k") or 0),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    if tool == "google_workspace":
        return json.dumps(
            {
                "tool": tool,
                "action": action,
                "query": _normalize_text((args or {}).get("query")),
                "message_id": _normalize_text((args or {}).get("message_id")),
                "calendar_id": _normalize_text((args or {}).get("calendar_id")),
                "event_start": _normalize_text((args or {}).get("event_start")),
                "event_end": _normalize_text((args or {}).get("event_end")),
                "docs_title": _normalize_text((args or {}).get("docs_title")),
                "email_subject": _normalize_text((args or {}).get("email_subject")),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    if tool == "device":
        return json.dumps(
            {
                "tool": tool,
                "action": action,
                "url": _normalize_url((args or {}).get("url")),
                "route": _normalize_text((args or {}).get("route")),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    if tool == "screen_get":
        return json.dumps(
            {
                "tool": tool,
                "display_id": _normalize_text((args or {}).get("display_id")),
                "format": _normalize_text((args or {}).get("format")) or "jpeg",
                "max_edge": int((args or {}).get("max_edge") or 1280),
                "quality": int((args or {}).get("quality") or 72),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    if tool == "execute":
        return json.dumps(
            {
                "tool": tool,
                "command": _normalize_text((args or {}).get("command")),
                "cwd": _normalize_text((args or {}).get("cwd")),
                "timeout_ms": int((args or {}).get("timeout_ms") or 0),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    if tool == "present_files":
        return json.dumps(
            {
                "tool": tool,
                "filepaths": _normalize_filepaths((args or {}).get("filepaths")),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    return json.dumps({"tool": tool, "args": args or {}}, ensure_ascii=False, sort_keys=True)


def _tool_attempt_limit(name: str) -> int:
    return {
        "web_search": 4,
        "attachment_search": 3,
        "memory_search": 4,
        "google_workspace": 4,
        "device": 2,
        "screen_get": 2,
        "execute": 4,
        "present_files": 3,
    }.get(str(name or "").strip().lower(), 2)


def _duplicate_signature_limit(name: str, args: dict[str, Any]) -> int:
    return 1


def result_has_progress(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    if bool(result.get("no_new_info")):
        return False
    total = result.get("total")
    if isinstance(total, int):
        return total > 0
    for key in ("items", "hits", "event_attendees", "artifacts"):
        value = result.get(key)
        if isinstance(value, list) and len(value) > 0:
            return True
    item = result.get("item")
    if isinstance(item, dict) and bool(item):
        return True
    raw = result.get("raw")
    if isinstance(raw, dict) and bool(raw):
        return True
    for key in (
        "content",
        "data_url",
        "document_id",
        "url",
        "route",
        "summary",
        "detail",
        "stdout",
        "stderr",
    ):
        if str(result.get(key) or "").strip():
            return True
    return False


def _invalid_reason(name: str, args: dict[str, Any]) -> str:
    tool = str(name or "").strip().lower()
    action = _normalize_text((args or {}).get("action"))
    if tool == "web_search":
        if not _normalize_text((args or {}).get("query")):
            return "invalid web_search call: provide a non-empty query before calling web_search"
    if tool == "attachment_search":
        if not _normalize_text((args or {}).get("query")):
            return "invalid attachment_search call: provide a non-empty query before searching attachments"
    if tool == "memory_search":
        if not _normalize_text((args or {}).get("query")):
            return "invalid memory_search call: provide a non-empty query before searching long-term memory"
    if tool == "google_workspace":
        if not action:
            return "invalid google_workspace call: provide a concrete action before calling google_workspace"
        if action == "gmail_get" and not _normalize_text((args or {}).get("message_id")):
            return "invalid google_workspace call: gmail_get requires message_id"
        if action == "calendar_create_event":
            if not _normalize_text((args or {}).get("event_summary")):
                return "invalid google_workspace call: calendar_create_event requires event_summary"
            if not _normalize_text((args or {}).get("event_start")) or not _normalize_text((args or {}).get("event_end")):
                return "invalid google_workspace call: calendar_create_event requires event_start and event_end"
        if action in {"gmail_send", "gmail_draft"}:
            recipients = list((args or {}).get("email_to") or [])
            if not recipients:
                return f"invalid google_workspace call: {action} requires email_to"
            if not _normalize_text((args or {}).get("email_subject")):
                return f"invalid google_workspace call: {action} requires email_subject"
    if tool == "device":
        if action not in {"status", "open_url", "open_aelin"}:
            return "invalid device call: action must be one of status, open_url, open_aelin"
        if action == "open_url" and not _normalize_url((args or {}).get("url")):
            return "invalid device call: open_url requires a non-empty http(s) url"
    if tool == "execute":
        command = str((args or {}).get("command") or "").strip()
        if not command:
            return "invalid execute call: provide a non-empty command"
        if len(command) > 4000:
            return "invalid execute call: command is too long"
    if tool == "present_files":
        filepaths = _normalize_filepaths((args or {}).get("filepaths"))
        if not filepaths:
            return "invalid present_files call: provide at least one file path"
        if len(filepaths) > 16:
            return "invalid present_files call: too many file paths"
    return ""


def classify_tool_call(name: str, args: dict[str, Any]) -> bool:
    tool = str(name or "").strip().lower()
    action = str((args or {}).get("action") or "").strip().lower()

    if tool == "device":
        return action in {"open_url", "open_aelin"}
    if tool in {"web_search", "attachment_search", "memory_search", "screen_get", "present_files"}:
        return False
    if tool == "execute":
        return True
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
        consecutive_failures_limit: int = 3,
        consecutive_no_progress_limit: int = 2,
    ) -> None:
        self.max_tool_calls = max(1, int(max_tool_calls or 1))
        self.max_write_calls = max(0, int(max_write_calls or 0))
        self.allow_write_tools = bool(allow_write_tools)
        self.consecutive_failures_limit = max(1, int(consecutive_failures_limit or 1))
        self.consecutive_no_progress_limit = max(1, int(consecutive_no_progress_limit or 1))

    def evaluate(self, *, name: str, args: dict[str, Any], usage: ToolPolicyUsage) -> ToolPolicyDecision:
        tool = str(name or "").strip().lower()
        if tool not in {
            "device",
            "web_search",
            "attachment_search",
            "memory_search",
            "screen_get",
            "google_workspace",
            "execute",
            "present_files",
        }:
            return ToolPolicyDecision(allowed=False, is_write=False, reason="unsupported_tool")

        invalid_reason = _invalid_reason(tool, args)
        if invalid_reason:
            return ToolPolicyDecision(allowed=False, is_write=False, reason=invalid_reason)

        if usage.consecutive_failures >= self.consecutive_failures_limit:
            return ToolPolicyDecision(
                allowed=False,
                is_write=False,
                reason="tool_run_stalled: recent tool attempts kept failing; stop calling tools and answer from current evidence",
            )
        if usage.consecutive_no_progress >= self.consecutive_no_progress_limit:
            return ToolPolicyDecision(
                allowed=False,
                is_write=False,
                reason="tool_run_no_progress: recent tool attempts added no new information; stop using tools and answer from current evidence",
            )

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

        tool_limit_deny = _deny_if_over_limit(
            current=usage.tool_counts.get(tool, 0),
            limit=_tool_attempt_limit(tool),
            reason=f"{tool}_call_limit: this tool has already been used enough in this run; answer from current evidence",
            is_write=is_write,
        )
        if tool_limit_deny is not None:
            return tool_limit_deny

        signature = build_tool_signature(tool, args)
        duplicate_limit = _duplicate_signature_limit(tool, args)
        if usage.signature_counts.get(signature, 0) >= duplicate_limit:
            return ToolPolicyDecision(
                allowed=False,
                is_write=is_write,
                reason=f"duplicate_{tool}_call: do not repeat the same {tool} arguments; reuse current evidence or change the request materially",
            )

        return ToolPolicyDecision(allowed=True, is_write=is_write, reason="ok")
