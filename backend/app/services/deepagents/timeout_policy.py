from __future__ import annotations

from time import perf_counter
from typing import Any

from app.settings import settings


_IO_BOUND_TOOL_NAMES = {
    "attachment_search",
    "google_workspace",
    "screen_get",
    "web_search",
}


def read_model_node_timeout_seconds() -> float:
    try:
        return max(15.0, float(getattr(settings, "deepagents_run_timeout_seconds", 180.0) or 180.0))
    except Exception:
        return 180.0


def read_run_budget_seconds() -> float:
    try:
        return max(30.0, float(getattr(settings, "deepagents_run_budget_seconds", 900.0) or 900.0))
    except Exception:
        return 900.0


def read_stream_idle_timeout_seconds(*, request_timeout_seconds: float | None = None) -> float:
    try:
        configured_idle = max(
            5.0,
            float(getattr(settings, "deepagents_stream_idle_timeout_seconds", 180.0) or 180.0),
        )
    except Exception:
        configured_idle = 180.0
    baseline = max(configured_idle, read_model_node_timeout_seconds())
    request_timeout = max(0.0, float(request_timeout_seconds or 0.0))
    if request_timeout > 0:
        return min(request_timeout, baseline)
    return baseline


def _legacy_tool_timeout_seconds() -> float:
    try:
        return max(1.0, float(getattr(settings, "deepagents_tool_timeout_seconds", 30.0) or 30.0))
    except Exception:
        return 30.0


def _fast_tool_timeout_seconds() -> float:
    legacy = _legacy_tool_timeout_seconds()
    try:
        return max(1.0, float(getattr(settings, "deepagents_tool_timeout_seconds_fast", legacy) or legacy))
    except Exception:
        return legacy


def _io_tool_timeout_seconds() -> float:
    legacy = _legacy_tool_timeout_seconds()
    default_value = max(legacy, 90.0)
    try:
        return max(1.0, float(getattr(settings, "deepagents_tool_timeout_seconds_io", default_value) or default_value))
    except Exception:
        return default_value


def _execute_tool_timeout_seconds() -> float:
    legacy = _legacy_tool_timeout_seconds()
    desktop_default = max(
        5.0,
        float(getattr(settings, "desktop_plugin_execute_timeout_seconds", 120.0) or 120.0),
    )
    default_value = max(legacy, desktop_default + 3.0, 180.0)
    try:
        return max(
            1.0,
            float(getattr(settings, "deepagents_tool_timeout_seconds_execute", default_value) or default_value),
        )
    except Exception:
        return default_value


def requested_execute_timeout_seconds(args: dict[str, Any] | None) -> float | None:
    try:
        timeout_ms = int((args or {}).get("timeout_ms") or 0)
    except Exception:
        return None
    if timeout_ms <= 0:
        return None
    timeout_ms = max(1_000, min(120_000, timeout_ms))
    return timeout_ms / 1000.0


def remaining_run_budget_seconds(
    *,
    run_started_monotonic: float | None,
    run_budget_seconds: float | None,
    now_monotonic: float | None = None,
) -> float | None:
    if run_started_monotonic is None or run_budget_seconds is None:
        return None
    budget = float(run_budget_seconds or 0.0)
    if budget <= 0:
        return None
    now_value = float(now_monotonic) if now_monotonic is not None else perf_counter()
    remaining = budget - (now_value - float(run_started_monotonic))
    return max(0.0, remaining)


def select_tool_timeout_seconds(
    *,
    name: str,
    args: dict[str, Any] | None = None,
    remaining_budget_seconds: float | None = None,
) -> float:
    tool_name = str(name or "").strip()
    if tool_name == "execute":
        timeout_seconds = _execute_tool_timeout_seconds()
        requested_timeout = requested_execute_timeout_seconds(args)
        if requested_timeout is not None:
            timeout_seconds = max(timeout_seconds, requested_timeout + 5.0)
    elif tool_name in _IO_BOUND_TOOL_NAMES:
        timeout_seconds = _io_tool_timeout_seconds()
    else:
        timeout_seconds = _fast_tool_timeout_seconds()

    if remaining_budget_seconds is not None:
        timeout_seconds = min(timeout_seconds, max(1.0, float(remaining_budget_seconds)))
    return max(1.0, timeout_seconds)
