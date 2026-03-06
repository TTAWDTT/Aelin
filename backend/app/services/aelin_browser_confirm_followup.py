from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.schemas import AelinBrowserConfirmRequest, AelinChatRequest
from app.services.browser_runtime_login import browser_runtime_login_service


_LOG = logging.getLogger(__name__)


def dispatch_followup_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
):
    from app.routers import aelin_chat as aelin_chat_router

    return aelin_chat_router._dispatch_aelin_chat(payload, db, current_user, event_cb=None)


def build_followup_request(
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


def resolve_confirm_controls(
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


def continue_after_browser_confirm(
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
        followup_request = build_followup_request(payload=followup_payload, workspace=workspace)
        followup = dispatch_followup_chat(
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


def resolve_confirm_login_state(
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

    return browser_runtime_login_service.resolve_login_pending(
        user_id=int(current_user.id),
        workspace=workspace,
        request_id=str(payload.login_request_id or ""),
        profile_id=profile_id,
        status=resolved_status,
    )


def build_confirm_message(*, ok: bool, continued: bool, continuation_error: str, result: dict[str, Any]) -> str:
    if not ok:
        return f"确认后执行失败：{str(result.get('error') or 'unknown')[:160]}"
    if continued:
        return "已确认并继续执行任务。"
    if continuation_error:
        return f"已确认并执行浏览器步骤，但自动继续失败：{continuation_error}"
    return "已确认并执行浏览器步骤。"
