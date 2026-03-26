from __future__ import annotations

from typing import Any

from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.foundation.google_workspace_cli import get_google_workspace_cli_service
from app.services.tools.tool_helpers import _safe_int


_GWS_WRITE_ACTIONS = {"calendar_create_event", "gmail_send", "gmail_draft", "docs_create"}


def _scope_failure(scope: str, result: dict[str, Any], *, stop_retry: bool = False) -> dict[str, Any]:
    payload = {"ok": False, "scope": scope, **result}
    if stop_retry:
        payload["stop_retry"] = True
    return payload


def _scope_items(scope: str, result: dict[str, Any]) -> dict[str, Any]:
    items = list(result.get("items") or [])
    return {
        "ok": True,
        "scope": scope,
        "items": items,
        "raw": result.get("raw") or result.get("data") or {},
        "no_new_info": len(items) == 0,
        "summary": f"{scope} returned {len(items)} item(s)",
    }


def _scope_item(scope: str, result: dict[str, Any]) -> dict[str, Any]:
    item = result.get("item") if isinstance(result.get("item"), dict) else {}
    return {
        "ok": True,
        "scope": scope,
        "item": item,
        "raw": result.get("raw") or result.get("data") or {},
        "no_new_info": not bool(item),
        "summary": f"{scope} returned {'1 item' if item else 'no item'}",
    }


def _normalize_gws_error(error: str, *, action: str, is_write: bool) -> str:
    err = str(error or "").strip() or "google_workspace_failed"
    if err == "gws_not_installed":
        return (
            "google_workspace unavailable: gws is not installed on this machine; stop calling google_workspace and tell the user to install or configure gws first"
        )
    if err == "gws_timeout":
        return (
            "google_workspace timeout: the CLI did not finish in time; retry at most once with corrected arguments, otherwise stop using google_workspace in this run"
        )
    if err.startswith("gws_failed:"):
        suffix = err.split(":", 1)[1]
        if "login" in suffix.lower() or "auth" in suffix.lower() or "credential" in suffix.lower():
            return (
                "google_workspace authorization failed: gws is not authenticated; stop calling google_workspace and ask the user to run gws auth login"
            )
        if is_write:
            return f"google_workspace write failed during {action}: {suffix}. Do not retry the same write blindly."
        return f"google_workspace action failed during {action}: {suffix}"
    return err


def _validate_action_args(action: str, args: dict[str, Any]) -> str:
    if action in {"runtime", "status", "auth_status"}:
        return ""
    if action == "gmail_list":
        return ""
    if action == "gmail_get":
        if not str(args.get("message_id") or "").strip():
            return "gmail_get requires message_id"
        return ""
    if action == "drive_list":
        return ""
    if action == "calendar_list":
        return ""
    if action == "calendar_create_event":
        if not str(args.get("event_summary") or "").strip():
            return "calendar_create_event requires event_summary"
        if not str(args.get("event_start") or "").strip() or not str(args.get("event_end") or "").strip():
            return "calendar_create_event requires event_start and event_end"
        return ""
    if action in {"gmail_send", "gmail_draft"}:
        if not list(args.get("email_to") or []):
            return f"{action} requires email_to"
        if not str(args.get("email_subject") or "").strip():
            return f"{action} requires email_subject"
        if not str(args.get("email_body") or "").strip():
            return f"{action} requires email_body"
        return ""
    if action == "docs_create":
        return ""
    return "unsupported_action"


def _guard_runtime_and_auth(service: Any, *, action: str) -> dict[str, Any] | None:
    if action in {"runtime", "status", "auth_status"}:
        return None
    runtime = service.runtime_status()
    if not bool(runtime.get("available")):
        return _scope_failure(
            "google_workspace",
            {
                "error": _normalize_gws_error("gws_not_installed", action=action, is_write=action in _GWS_WRITE_ACTIONS),
                "login_command": runtime.get("login_command") or service.login_command(),
                "install_hint": runtime.get("install_hint") or service.install_hint(),
            },
            stop_retry=True,
        )
    auth = service.auth_status()
    if not bool(auth.get("authenticated")):
        return _scope_failure(
            "google_workspace",
            {
                "error": "google_workspace authorization required: stop calling google_workspace and ask the user to run gws auth login",
                "login_command": auth.get("login_command") or service.login_command(),
                "email": auth.get("email") or "",
            },
            stop_retry=True,
        )
    return None


def _finalize_result(scope: str, action: str, result: dict[str, Any]) -> dict[str, Any]:
    if bool(result.get("ok")):
        return _scope_item(scope, result) if scope in {"docs"} and isinstance(result.get("item"), dict) else (
            _scope_items(scope, result) if isinstance(result.get("items"), list) else _scope_item(scope, result)
        )
    return _scope_failure(
        scope,
        {
            **result,
            "error": _normalize_gws_error(
                str(result.get("error") or ""),
                action=action,
                is_write=action in _GWS_WRITE_ACTIONS,
            ),
        },
        stop_retry=action in _GWS_WRITE_ACTIONS or str(result.get("error") or "") in {"gws_not_installed", "gws_timeout"},
    )


def tool_google_workspace(_context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch Google Workspace tool actions to the local gws CLI wrapper."""

    action = str(args.get("action") or "").strip().lower()
    service = get_google_workspace_cli_service()
    validation_error = _validate_action_args(action, args)
    if validation_error:
        return _scope_failure(
            "google_workspace",
            {
                "error": f"invalid google_workspace call: {validation_error}. Correct the arguments once instead of retrying blindly.",
            },
            stop_retry=False,
        )

    runtime_guard = _guard_runtime_and_auth(service, action=action)
    if runtime_guard is not None:
        return runtime_guard

    if action in {"runtime", "status"}:
        # status 作为别名，方便迁移旧的 google_status 语义。
        return {**service.runtime_status(), "scope": "runtime"}

    if action == "auth_status":
        result = service.auth_status()
        # 补充 login_command，方便 Agent 在“已安装但未登录”场景下给出具体指令。
        if not bool(result.get("authenticated", True)):
            result = {**result, "login_command": service.login_command()}
        return {**result, "scope": "auth"}

    if action == "gmail_list":
        query = str(args.get("query") or "").strip()
        max_results = _safe_int(args.get("max_results") or 10, 10, low=1, high=50)
        include_spam_trash = bool(args.get("include_spam_trash"))
        result = service.gmail_list_messages(
            query=query,
            max_results=max_results,
            include_spam_trash=include_spam_trash,
        )
        return _finalize_result("gmail", action, result)

    if action == "gmail_get":
        message_id = str(args.get("message_id") or "").strip()
        if not message_id:
            return _scope_failure("gmail", {"error": "missing_message_id"})
        fmt = str(args.get("format") or "full").strip().lower()
        result = service.gmail_get_message(message_id=message_id, fmt=fmt)
        return _finalize_result("gmail", action, result)

    if action == "drive_list":
        query = str(args.get("query") or "").strip()
        max_results = _safe_int(args.get("max_results") or 10, 10, low=1, high=50)
        result = service.drive_list_files(query=query, max_results=max_results)
        return _finalize_result("drive", action, result)

    if action == "calendar_list":
        calendar_id = str(args.get("calendar_id") or "primary").strip() or "primary"
        time_min = str(args.get("time_min") or "").strip()
        time_max = str(args.get("time_max") or "").strip()
        max_results = _safe_int(args.get("max_results") or 10, 10, low=1, high=50)
        single_events = bool(args.get("single_events", True))
        result = service.calendar_list_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            single_events=single_events,
        )
        return _finalize_result("calendar", action, result)

    if action == "calendar_create_event":
        calendar_id = str(args.get("calendar_id") or "primary").strip() or "primary"
        summary = str(args.get("event_summary") or "").strip()
        description = str(args.get("event_description") or "").strip()
        event_start = str(args.get("event_start") or "").strip()
        event_end = str(args.get("event_end") or "").strip()
        attendees = list(args.get("event_attendees") or [])
        result = service.calendar_create_event(
            calendar_id=calendar_id,
            summary=summary,
            description=description,
            start=event_start,
            end=event_end,
            attendees=attendees,
        )
        return _finalize_result("calendar", action, result)

    if action == "gmail_send":
        to = list(args.get("email_to") or [])
        cc = list(args.get("email_cc") or [])
        bcc = list(args.get("email_bcc") or [])
        subject = str(args.get("email_subject") or "").strip()
        body = str(args.get("email_body") or "")
        result = service.gmail_send_message(
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body=body,
        )
        return _finalize_result("gmail", action, result)

    if action == "gmail_draft":
        to = list(args.get("email_to") or [])
        cc = list(args.get("email_cc") or [])
        bcc = list(args.get("email_bcc") or [])
        subject = str(args.get("email_subject") or "").strip()
        body = str(args.get("email_body") or "")
        result = service.gmail_create_draft(
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body=body,
        )
        return _finalize_result("gmail", action, result)

    if action == "docs_create":
        title = str(args.get("docs_title") or "").strip()
        content = str(args.get("docs_content") or "").strip()
        result = service.docs_create_document(title=title or "Aelin 文档")
        if not bool(result.get("ok")):
            return _finalize_result("docs", action, result)
        item = result.get("item") if isinstance(result.get("item"), dict) else {}
        document_id = str(item.get("documentId") or item.get("document_id") or "").strip()
        web_url = ""
        if document_id:
            web_url = f"https://docs.google.com/document/d/{document_id}/edit"
            item.setdefault("webViewLink", web_url)
        append_ok = None
        append_error = ""
        if content and document_id:
            append_result = service.docs_append_text(document_id=document_id, text=content)
            append_ok = bool(append_result.get("ok"))
            if not append_ok:
                append_error = _normalize_gws_error(
                    str(append_result.get("error") or "")[:180],
                    action=action,
                    is_write=True,
                )
        response: dict[str, Any] = {
            "ok": True,
            "scope": "docs",
            "item": item,
            "raw": result.get("raw") or result.get("data") or {},
        }
        if document_id:
            response["document_id"] = document_id
        if web_url:
            response["web_url"] = web_url
        if append_ok is not None:
            response["append_ok"] = append_ok
            if append_error:
                response["append_error"] = append_error
        return response

    return _scope_failure("google_workspace", {"error": "unsupported_action"})

