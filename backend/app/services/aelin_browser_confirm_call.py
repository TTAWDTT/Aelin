from __future__ import annotations

from typing import Any

from app.services.browser_automation import browser_automation_service
from app.services.browser_exec import run_sync_playwright_call


def is_cdp_restart_error(error: str) -> bool:
    clean = str(error or "").strip().lower()
    if not clean:
        return False
    normalized = clean
    if normalized.startswith("cdp_unavailable:"):
        normalized = normalized.split(":", 1)[1].strip()
    return clean in {
        "browser_restart_required_for_cdp",
        "browser_restart_confirmation_required",
        "browser_restart_failed_for_cdp",
        "cdp_conflict_process_still_running",
        "cdp_launch_timeout",
    } or normalized in {
        "browser_restart_required_for_cdp",
        "browser_restart_confirmation_required",
        "browser_restart_failed_for_cdp",
        "cdp_conflict_process_still_running",
        "cdp_launch_timeout",
    } or "cdp_requires_browser_restart" in clean or "cdp_requires_browser_restart" in normalized


def build_browser_restart_meta(restart_meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = restart_meta if isinstance(restart_meta, dict) else {}
    return {
        "attempted": True,
        "ok": bool(meta.get("ok")),
        "error": str(meta.get("error") or "")[:180],
        "probe_reason": str(meta.get("probe_reason") or "")[:160],
        "probe_listener_count": int(meta.get("probe_listener_count") or 0),
        "probe_listener_pids": list(meta.get("probe_listener_pids") or []),
        "terminated_pids": list(meta.get("terminated_pids") or []),
        "killed_pids": list(meta.get("killed_pids") or []),
        "failed_pids": list(meta.get("failed_pids") or []),
        "remaining_pids": list(meta.get("remaining_pids") or []),
    }


def needs_restart_before_confirmed_call(*, tool_name: str, scope: str, clean_args: dict[str, Any]) -> bool:
    if tool_name != "browser_state_get":
        return False
    if str(scope or "").strip().lower() != "cdp":
        return False
    return bool(clean_args.get("include_dom")) or bool(clean_args.get("include_a11y"))


def build_restart_failed_result(*, error: str, scope: str, restart_meta: dict[str, Any] | None) -> dict[str, Any]:
    result = {
        "ok": False,
        "error": str(error or "cdp_launch_timeout")[:180] or "cdp_launch_timeout",
        "scope": str(scope or "cdp")[:32] or "cdp",
    }
    if str(scope or "").strip().lower() == "cdp":
        result["requires_cdp"] = True
    result["restart"] = build_browser_restart_meta(restart_meta)
    return result


def normalize_confirm_browser_use(
    *, action: str, raw_args: dict[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    allowed_keys = {
        "url",
        "target",
        "selector",
        "text",
        "value",
        "strategy",
        "role",
        "press_enter",
        "direction",
        "amount",
        "wait_ms",
        "timeout_ms",
        "scope",
        "confirm",
    }
    clean_args = {str(k): v for k, v in raw_args.items() if str(k) in allowed_keys}
    clean_args["confirm"] = True
    scope = str(clean_args.get("scope") or "cdp").strip().lower()
    if scope not in {"auto", "cdp", "external"}:
        scope = "cdp"
    if action != "navigate" and scope == "external":
        scope = "cdp"
    clean_args["scope"] = scope
    return action, scope, clean_args


def normalize_confirm_browser_state_get(raw_args: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    allowed_keys = {
        "scope",
        "include_dom",
        "include_a11y",
        "max_targets",
        "max_items",
        "pid",
    }
    clean_args = {str(k): v for k, v in raw_args.items() if str(k) in allowed_keys}
    scope = str(clean_args.get("scope") or "cdp").strip().lower()
    if scope not in {"auto", "cdp", "external", "system", "all"}:
        scope = "cdp"
    clean_args["scope"] = "cdp" if scope != "system" else scope
    return "state_get", str(clean_args.get("scope") or "cdp"), clean_args


def execute_confirmed_browser_call(
    *,
    tool_name: str,
    action: str,
    scope: str,
    clean_args: dict[str, Any],
    user_id: int,
    workspace: str,
    profile_id: str = "",
) -> dict[str, Any]:
    profile_value = str(profile_id or "").strip()
    if tool_name == "browser_use":
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "workspace": workspace,
            "action": action,
            "args": clean_args,
            "scope": scope,
        }
        if profile_value:
            kwargs["profile_id"] = profile_value
        return run_sync_playwright_call(browser_automation_service.use, **kwargs)
    kwargs = {
        "user_id": user_id,
        "workspace": workspace,
        "scope": scope,
        "include_dom": bool(clean_args.get("include_dom", False)),
        "include_a11y": bool(clean_args.get("include_a11y", False)),
        "max_targets": int(clean_args.get("max_targets") or 30),
        "max_items": int(clean_args.get("max_items") or 20),
        "pid": int(clean_args.get("pid") or 0),
    }
    if profile_value:
        kwargs["profile_id"] = profile_value
    return run_sync_playwright_call(browser_automation_service.state_get, **kwargs)
