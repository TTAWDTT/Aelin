from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolPolicyDecision:
    allowed: bool
    is_write: bool
    reason: str = ""


@dataclass
class ToolPolicyUsage:
    round_calls: int = 0
    total_calls: int = 0
    write_calls: int = 0


def classify_tool_call(name: str, args: dict[str, Any]) -> bool:
    """Return True when the tool call is a write operation."""
    tool = str(name or "").strip().lower()
    action = str((args or {}).get("action") or "").strip().lower()

    if tool == "context_get":
        return False
    if tool == "profile":
        return action == "append_note"
    if tool == "device":
        return action in {"open_url", "open_aelin"}
    if tool == "web_search":
        return False
    if tool == "attachment_search":
        return False
    if tool == "screen_get":
        return False
    if tool == "google_workspace":
        # 读操作（runtime/auth_status/gmail_list/gmail_get/drive_list/calendar_list）视为只读；
        # 写操作在工具层预留，占位 action 统一视为写，以便配额与安全策略可以统一控制。
        return action in {"calendar_create_event", "gmail_send", "gmail_draft", "docs_create"}
    if tool == "skill":
        return False
    if tool == "plane":
        return action in {"delegate", "continue", "close"}
    if tool in {"pinchtab", "pinchtab_agent", "pinchtab_session"}:
        # PinchTab 调用会驱动真实浏览器行为，统一视为写操作以纳入配额控制。
        return True
    return False


def _deny_if_over_limit(*, current: int, limit: int, reason: str, is_write: bool = False) -> ToolPolicyDecision | None:
    if int(current) >= int(limit):
        return ToolPolicyDecision(allowed=False, is_write=is_write, reason=reason)
    return None


class AelinToolPolicy:
    def __init__(
        self,
        *,
        max_calls_per_round: int,
        max_tool_calls: int,
        max_write_calls: int,
        allow_write_tools: bool,
    ) -> None:
        self.max_calls_per_round = max(1, int(max_calls_per_round or 1))
        self.max_tool_calls = max(1, int(max_tool_calls or 1))
        self.max_write_calls = max(0, int(max_write_calls or 0))
        self.allow_write_tools = bool(allow_write_tools)

    def evaluate(self, *, name: str, args: dict[str, Any], usage: ToolPolicyUsage) -> ToolPolicyDecision:
        tool = str(name or "").strip().lower()
        if tool not in {
            "context_get",
            "profile",
            "device",
            "web_search",
            "attachment_search",
            "screen_get",
            "google_workspace",
            "skill",
            "plane",
            "pinchtab",
            "pinchtab_agent",
            "pinchtab_session",
        }:
            return ToolPolicyDecision(allowed=False, is_write=False, reason="unsupported_tool")

        round_limit_deny = _deny_if_over_limit(
            current=usage.round_calls,
            limit=self.max_calls_per_round,
            reason="round_call_limit",
        )
        if round_limit_deny is not None:
            return round_limit_deny
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
