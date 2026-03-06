from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import User
from app.schemas import AelinBrowserConfirmRequest, AelinBrowserConfirmResponse, AelinChatRequest
from app.services.browser_automation import browser_automation_service
from app.services.browser_exec import run_sync_playwright_call


_LOG = logging.getLogger(__name__)


def _dispatch_followup_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
):
    from app.routers import aelin_chat as aelin_chat_router

    return aelin_chat_router._dispatch_aelin_chat(payload, db, current_user, event_cb=None)


def _is_cdp_restart_error(error: str) -> bool:
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


def _build_browser_restart_meta(restart_meta: dict[str, Any] | None) -> dict[str, Any]:
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


def _needs_restart_before_confirmed_call(*, tool_name: str, scope: str, clean_args: dict[str, Any]) -> bool:
    if tool_name != "browser_state_get":
        return False
    if str(scope or "").strip().lower() != "cdp":
        return False
    return bool(clean_args.get("include_dom")) or bool(clean_args.get("include_a11y"))


def _build_restart_failed_result(*, error: str, scope: str, restart_meta: dict[str, Any] | None) -> dict[str, Any]:
    result = {
        "ok": False,
        "error": str(error or "cdp_launch_timeout")[:180] or "cdp_launch_timeout",
        "scope": str(scope or "cdp")[:32] or "cdp",
    }
    if str(scope or "").strip().lower() == "cdp":
        result["requires_cdp"] = True
    result["restart"] = _build_browser_restart_meta(restart_meta)
    return result


def _normalize_confirm_browser_use(
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


def _normalize_confirm_browser_state_get(raw_args: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
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


def _build_followup_request(
    *, payload: AelinBrowserConfirmRequest, workspace: str
) -> AelinChatRequest:
    resume_query = str(payload.resume_query or "").strip()
    resume_request = payload.resume_request if isinstance(payload.resume_request, dict) else {}
    if resume_request:
        followup_request_payload = dict(resume_request)
        followup_request_payload["workspace"] = workspace
        followup_request_payload["use_memory"] = bool(followup_request_payload.get("use_memory", True))
        if not str(followup_request_payload.get("query") or "").strip():
            followup_request_payload["query"] = resume_query or "我已确认，请继续完成刚才的浏览器任务并直接给我结果。"
        return AelinChatRequest(**followup_request_payload)
    if not resume_query:
        resume_query = "我已确认，请继续完成刚才的浏览器任务并直接给我结果。"
    return AelinChatRequest(
        query=resume_query[:500],
        workspace=workspace,
        use_memory=True,
        history=[],
        images=[],
    )


def _resolve_confirm_controls(
    *,
    payload: AelinBrowserConfirmRequest,
    stored_login_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str, bool]:
    next_call = payload.next_call if isinstance(payload.next_call, dict) and payload.next_call else {}
    if (not next_call) and isinstance(stored_login_state.get("next_call"), dict):
        next_call = dict(stored_login_state.get("next_call") or {})

    resume_request = payload.resume_request if isinstance(payload.resume_request, dict) and payload.resume_request else {}
    if (not resume_request) and isinstance(stored_login_state.get("resume_request"), dict):
        resume_request = dict(stored_login_state.get("resume_request") or {})

    resume_query = str(payload.resume_query or "").strip() or str(stored_login_state.get("resume_query") or "").strip()
    payload_controls_resume = bool(payload.next_call) or bool(payload.resume_request) or bool(str(payload.resume_query or "").strip())
    if payload.continue_after_confirm is False:
        continue_after_confirm = False
    elif payload_controls_resume:
        continue_after_confirm = bool(payload.continue_after_confirm)
    else:
        continue_after_confirm = bool(stored_login_state.get("continue_after_confirm", payload.continue_after_confirm))

    return next_call, resume_request, resume_query, continue_after_confirm


def _continue_after_browser_confirm(
    *,
    ok: bool,
    payload: AelinBrowserConfirmRequest,
    next_call: dict[str, Any],
    resume_request: dict[str, Any],
    resume_query: str,
    continue_after_confirm: bool,
    workspace: str,
    db: Session,
    current_user: User,
) -> tuple[bool, str, dict[str, Any]]:
    if not ok or not continue_after_confirm:
        return False, "", {}

    try:
        followup_payload = payload.model_copy(
            update={
                "next_call": next_call,
                "resume_request": resume_request,
                "resume_query": resume_query,
                "continue_after_confirm": continue_after_confirm,
            }
        )
        followup_request = _build_followup_request(payload=followup_payload, workspace=workspace)
        followup = _dispatch_followup_chat(
            followup_request,
            db,
            current_user,
        )
        return True, "", followup.model_dump() if followup is not None else {}
    except Exception as exc:
        continuation_error = str(exc)[:200]
        _LOG.warning(
            "aelin_browser_confirm continuation_failed uid=%s workspace=%s error=%s",
            int(current_user.id),
            workspace,
            continuation_error,
        )
        return False, continuation_error, {}


def _resolve_confirm_login_state(
    *,
    ok: bool,
    continued: bool,
    continuation_error: str,
    payload: AelinBrowserConfirmRequest,
    workspace: str,
    current_user: User,
    profile_id: str,
) -> dict[str, Any]:
    if not ok or not str(payload.login_request_id or "").strip():
        return {}

    resolved_status = "confirmed"
    if continued:
        resolved_status = "continued"
    elif continuation_error:
        resolved_status = "continue_failed"

    return browser_automation_service.resolve_login_pending(
        user_id=int(current_user.id),
        workspace=workspace,
        request_id=str(payload.login_request_id or ""),
        profile_id=profile_id,
        status=resolved_status,
    )


def _build_confirm_message(*, ok: bool, continued: bool, continuation_error: str, result: dict[str, Any]) -> str:
    if not ok:
        return f"确认后执行失败：{str(result.get('error') or 'unknown')[:160]}"
    if continued:
        return "已确认并继续执行任务。"
    if continuation_error:
        return f"已确认并执行浏览器步骤，但自动继续失败：{continuation_error}"
    return "已确认并执行浏览器步骤。"


def confirm_browser_action_request(
    *,
    payload: AelinBrowserConfirmRequest,
    db: Session,
    current_user: User,
) -> AelinBrowserConfirmResponse:
    workspace = str(payload.workspace or "default").strip()[:64] or "default"
    stored_login_state: dict[str, Any] = {}
    if str(payload.login_request_id or "").strip():
        stored_login_state = browser_automation_service.get_login_state(
            user_id=int(current_user.id),
            workspace=workspace,
            request_id=str(payload.login_request_id or ""),
            profile_id=str(payload.profile_id or ""),
        )

    next_call, effective_resume_request, effective_resume_query, effective_continue_after_confirm = (
        _resolve_confirm_controls(payload=payload, stored_login_state=stored_login_state)
    )
    tool_name = str(next_call.get("tool") or "").strip().lower()
    if tool_name not in {"browser_use", "browser_state_get"}:
        raise HTTPException(status_code=400, detail="unsupported_next_call_tool")

    action = str(next_call.get("action") or payload.action or "").strip().lower()
    if tool_name == "browser_use" and action not in {"navigate", "click", "type", "scroll", "wait"}:
        raise HTTPException(status_code=400, detail="invalid_next_call_action")
    if tool_name == "browser_state_get" and action not in {"", "state_get"}:
        raise HTTPException(status_code=400, detail="invalid_next_call_action")

    raw_args = next_call.get("args")
    args = raw_args if isinstance(raw_args, dict) else {}
    if tool_name == "browser_use":
        action, scope, clean_args = _normalize_confirm_browser_use(action=action, raw_args=args)
    else:
        action, scope, clean_args = _normalize_confirm_browser_state_get(args)

    restart_meta: dict[str, Any] | None = None
    pre_restart_meta: dict[str, Any] | None = None
    if _needs_restart_before_confirmed_call(tool_name=tool_name, scope=scope, clean_args=clean_args):
        restart_meta = browser_automation_service.force_restart_to_cdp(
            timeout_seconds=24.0,
            user_id=int(current_user.id),
            workspace=workspace,
            profile_id=str(payload.profile_id or ""),
        )
        if bool(restart_meta.get("ok")):
            result = execute_confirmed_browser_call(
                tool_name=tool_name,
                action=action,
                scope="cdp",
                clean_args=clean_args,
                user_id=int(current_user.id),
                workspace=workspace,
                profile_id=str(payload.profile_id or ""),
            )
            if not isinstance(result, dict):
                result = _build_restart_failed_result(
                    error="browser_confirm_retry_invalid_payload",
                    scope="cdp",
                    restart_meta=restart_meta,
                )
            else:
                result = dict(result)
                result["restart"] = _build_browser_restart_meta(restart_meta)
        else:
            result = _build_restart_failed_result(
                error=str(restart_meta.get("error") or "cdp_launch_timeout"),
                scope="cdp",
                restart_meta=restart_meta,
            )
    else:
        result = execute_confirmed_browser_call(
            tool_name=tool_name,
            action=action,
            scope=scope,
            clean_args=clean_args,
            user_id=int(current_user.id),
            workspace=workspace,
            profile_id=str(payload.profile_id or ""),
        )
        pre_restart_meta = result.get("restart") if isinstance(result.get("restart"), dict) else None
        if (not bool(result.get("ok"))) and _is_cdp_restart_error(str(result.get("error") or "")):
            restart_meta = browser_automation_service.force_restart_to_cdp(
                timeout_seconds=24.0,
                user_id=int(current_user.id),
                workspace=workspace,
                profile_id=str(payload.profile_id or ""),
            )
            if bool(restart_meta.get("ok")):
                retry = execute_confirmed_browser_call(
                    tool_name=tool_name,
                    action=action,
                    scope="cdp",
                    clean_args=clean_args,
                    user_id=int(current_user.id),
                    workspace=workspace,
                    profile_id=str(payload.profile_id or ""),
                )
                if isinstance(retry, dict):
                    result = dict(retry)
                else:
                    result = {"ok": False, "error": "browser_confirm_retry_invalid_payload"}
            result = dict(result if isinstance(result, dict) else {})
            result["restart"] = _build_browser_restart_meta(restart_meta)

    _LOG.info(
        "aelin_browser_confirm uid=%s workspace=%s action=%s scope=%s ok=%s error=%s restart=%s pre_restart=%s restart_error=%s remaining_pids=%s",
        int(current_user.id),
        workspace,
        action,
        scope,
        bool(result.get("ok")),
        str(result.get("error") or "")[:160],
        "1" if restart_meta is not None else "0",
        "1" if pre_restart_meta is not None else "0",
        str((restart_meta or pre_restart_meta or {}).get("error") or "")[:160],
        len(list((restart_meta or pre_restart_meta or {}).get("remaining_pids") or [])),
    )

    ok = bool(result.get("ok"))
    continued, continuation_error, followup_result = _continue_after_browser_confirm(
        ok=ok,
        payload=payload,
        next_call=next_call,
        resume_request=effective_resume_request,
        resume_query=effective_resume_query,
        continue_after_confirm=effective_continue_after_confirm,
        workspace=workspace,
        db=db,
        current_user=current_user,
    )
    login_state = _resolve_confirm_login_state(
        ok=ok,
        continued=continued,
        continuation_error=continuation_error if effective_continue_after_confirm else "",
        payload=payload,
        workspace=workspace,
        current_user=current_user,
        profile_id=str(payload.profile_id or ""),
    )
    message = _build_confirm_message(
        ok=ok,
        continued=continued,
        continuation_error=continuation_error,
        result=result,
    )
    requires_followup = bool(ok and effective_continue_after_confirm and not continued)
    return AelinBrowserConfirmResponse(
        ok=ok,
        message=message,
        requires_followup=requires_followup,
        profile_id=str(payload.profile_id or result.get("profile_id") or ""),
        login_request_id=str(payload.login_request_id or result.get("login_request_id") or ""),
        login_state=login_state,
        tool_result=result if isinstance(result, dict) else {},
        continued=continued,
        continuation_error=continuation_error,
        followup_result=followup_result,
        generated_at=datetime.now(timezone.utc),
    )
