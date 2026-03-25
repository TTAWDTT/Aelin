from __future__ import annotations

from typing import Any

from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.foundation.google_workspace_cli import get_google_workspace_cli_service
from app.services.tools.tool_helpers import _safe_int


def _scope_failure(scope: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "scope": scope, **result}


def _scope_items(scope: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "scope": scope,
        "items": list(result.get("items") or []),
        "raw": result.get("raw") or result.get("data") or {},
    }


def _scope_item(scope: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "scope": scope,
        "item": result.get("item") if isinstance(result.get("item"), dict) else {},
        "raw": result.get("raw") or result.get("data") or {},
    }


def tool_google_workspace(_context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch Google Workspace tool actions to the local gws CLI wrapper."""

    action = str(args.get("action") or "").strip().lower()
    service = get_google_workspace_cli_service()

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
        return _scope_items("gmail", result) if bool(result.get("ok")) else _scope_failure("gmail", result)

    if action == "gmail_get":
        message_id = str(args.get("message_id") or "").strip()
        if not message_id:
            return _scope_failure("gmail", {"error": "missing_message_id"})
        fmt = str(args.get("format") or "full").strip().lower()
        result = service.gmail_get_message(message_id=message_id, fmt=fmt)
        return _scope_item("gmail", result) if bool(result.get("ok")) else _scope_failure("gmail", result)

    if action == "drive_list":
        query = str(args.get("query") or "").strip()
        max_results = _safe_int(args.get("max_results") or 10, 10, low=1, high=50)
        result = service.drive_list_files(query=query, max_results=max_results)
        return _scope_items("drive", result) if bool(result.get("ok")) else _scope_failure("drive", result)

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
        return _scope_items("calendar", result) if bool(result.get("ok")) else _scope_failure("calendar", result)

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
        return _scope_item("calendar", result) if bool(result.get("ok")) else _scope_failure("calendar", result)

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
        return _scope_item("gmail", result) if bool(result.get("ok")) else _scope_failure("gmail", result)

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
        return _scope_item("gmail", result) if bool(result.get("ok")) else _scope_failure("gmail", result)

    if action == "docs_create":
        title = str(args.get("docs_title") or "").strip()
        content = str(args.get("docs_content") or "").strip()
        result = service.docs_create_document(title=title or "Aelin 文档")
        if not bool(result.get("ok")):
            return _scope_failure("docs", result)
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
                append_error = str(append_result.get("error") or "")[:180]
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

