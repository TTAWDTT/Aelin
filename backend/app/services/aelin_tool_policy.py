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
    if tool == "diary":
        # Current diary tool only supports read/search actions.
        return False
    if tool == "profile":
        return action == "append_note"
    if tool == "tracking":
        return action in {"create", "run_once"}
    if tool == "device":
        return action == "mode_apply"
    if tool == "web_search":
        return False
    if tool == "screen_get":
        return False
    if tool == "browser_state_get":
        return False
    if tool == "browser_session_list":
        return False
    if tool == "browser_use":
        # Browser actions can mutate external state; treat as write for safety budgeting.
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
            "diary",
            "profile",
            "tracking",
            "device",
            "web_search",
            "screen_get",
            "browser_session_list",
            "browser_state_get",
            "browser_use",
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
