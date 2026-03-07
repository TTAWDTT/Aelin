from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import User
from app.schemas import AelinBrowserConfirmRequest, AelinBrowserConfirmResponse
from app.services.aelin_browser_confirm_call import (
    build_browser_restart_meta,
    build_restart_failed_result,
    execute_confirmed_browser_call,
    is_cdp_restart_error,
    needs_restart_before_confirmed_call,
    normalize_confirm_browser_state_get,
    normalize_confirm_browser_use,
)
from app.services.browser_plane import browser_plane_adapter
from app.services.aelin_browser_confirm_followup import (
    build_confirm_message,
    continue_after_browser_confirm,
    resolve_confirm_controls,
    resolve_confirm_login_state,
)


_LOG = logging.getLogger(__name__)


def confirm_browser_action_request(
    *,
    payload: AelinBrowserConfirmRequest,
    db: Session,
    current_user: User,
) -> AelinBrowserConfirmResponse:
    workspace = str(payload.workspace or "default").strip()[:64] or "default"
    stored_login_state: dict[str, Any] = {}
    if str(payload.login_request_id or "").strip():
        stored_login_state = browser_plane_adapter.get_login_state(
            user_id=int(current_user.id),
            workspace=workspace,
            request_id=str(payload.login_request_id or ""),
            profile_id=str(payload.profile_id or ""),
        )

    next_call, effective_resume_request, effective_resume_query, effective_continue_after_confirm = (
        resolve_confirm_controls(payload=payload, stored_login_state=stored_login_state)
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
        action, scope, clean_args = normalize_confirm_browser_use(action=action, raw_args=args)
    else:
        action, scope, clean_args = normalize_confirm_browser_state_get(args)

    restart_meta: dict[str, Any] | None = None
    pre_restart_meta: dict[str, Any] | None = None
    if needs_restart_before_confirmed_call(tool_name=tool_name, scope=scope, clean_args=clean_args):
        restart_meta = browser_plane_adapter.force_restart_to_cdp(
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
                result = build_restart_failed_result(
                    error="browser_confirm_retry_invalid_payload",
                    scope="cdp",
                    restart_meta=restart_meta,
                )
            else:
                result = dict(result)
                result["restart"] = build_browser_restart_meta(restart_meta)
        else:
            result = build_restart_failed_result(
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
        if (not bool(result.get("ok"))) and is_cdp_restart_error(str(result.get("error") or "")):
            restart_meta = browser_plane_adapter.force_restart_to_cdp(
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
            result["restart"] = build_browser_restart_meta(restart_meta)

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
    continued, continuation_error, followup_result = continue_after_browser_confirm(
        ok=ok,
        payload=payload,
        next_call=next_call,
        resume_request=effective_resume_request,
        resume_query=effective_resume_query,
        continue_after_confirm=effective_continue_after_confirm,
        workspace=workspace,
        current_user_id=int(current_user.id),
    )
    login_state = resolve_confirm_login_state(
        ok=ok,
        continued=continued,
        continuation_error=continuation_error if effective_continue_after_confirm else "",
        payload=payload,
        workspace=workspace,
        current_user_id=int(current_user.id),
        profile_id=str(payload.profile_id or ""),
    )
    message = build_confirm_message(
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
