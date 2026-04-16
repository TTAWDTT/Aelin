from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.models import User
from app.schemas import ChatAction, ChatRequest, ChatResponse, RemoteControlExecuteRequest
from app.services.device import device_actions
from app.services.device.device_contract import (
    SUPPORTED_DEVICE_ACTIONS,
    supported_deepagents_tools,
)
from app.services.device.remote_control_chat_adapter import (
    is_deepagents_no_result_response,
    run_chat_request,
)
from app.settings import settings

_LOCAL_FALLBACK_EMAIL = "local@example.com"
_LEGACY_LOCAL_FALLBACK_EMAILS = {"local@aelin.local"}
_REMOTE_URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
_REMOTE_STATUS_RE = re.compile(
    r"^(?:check\s+)?(?:device\s+|desktop\s+|computer\s+)?status$"
    r"|^(?:\u5e2e\u6211\u770b\u4e0b|\u5e2e\u6211\u67e5\u4e00\u4e0b|\u67e5\u770b|\u67e5\u4e00\u4e0b)?"
    r"(?:\u5f53\u524d)?(?:\u7535\u8111|\u8bbe\u5907)?\u72b6\u6001$",
    re.IGNORECASE,
)
_REMOTE_SCREENSHOT_RE = re.compile(
    r"^(?:screenshot|screen\s*shot|capture\s+screen)$"
    r"|^(?:\u622a\u56fe|\u622a\u4e2a\u56fe|\u622a\u5c4f|\u622a\u4e2a\u5c4f)$",
    re.IGNORECASE,
)
_REMOTE_OPEN_AELIN_RE = re.compile(
    r"^(?:open|launch)\s+aelin(?:\s+(?P<suffix>.+))?$"
    r"|^(?:\u6253\u5f00)\s*aelin(?:\s*(?P<suffix_cn>.+))?$",
    re.IGNORECASE,
)
_AELIN_ROUTE_ALIASES = {
    "home": "/",
    "chat": "/",
    "main": "/",
    "\u9996\u9875": "/",
    "\u4e3b\u9875": "/",
    "\u804a\u5929": "/",
    "settings": "/settings",
    "setting": "/settings",
    "\u8bbe\u7f6e": "/settings",
}


@dataclass(slots=True)
class ParsedRemoteCommand:
    kind: str
    args: dict[str, Any]


@dataclass(slots=True)
class RemoteCommandSource:
    source: str = "remote_control"
    user_name: str = ""
    open_id: str = ""
    chat_id: str = ""
    message_id: str = ""


@dataclass(slots=True)
class RemoteControlExecutionResult:
    ok: bool
    status: str
    response: ChatResponse


def resolve_remote_control_user(db: Session, *, bind_user_email: str | None = None) -> User:
    raw_email = getattr(settings, "feishu_bot_bind_user_email", "") if bind_user_email is None else bind_user_email
    configured_email = str(raw_email or "").strip().lower()
    if configured_email:
        bound = db.scalar(select(User).where(User.email == configured_email))
        if bound is not None:
            return bound
    user = db.scalar(select(User).order_by(User.id.asc()))
    if user is not None:
        if str(getattr(user, "email", "") or "").strip().lower() in _LEGACY_LOCAL_FALLBACK_EMAILS:
            user.email = _LOCAL_FALLBACK_EMAIL
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    return crud.create_user(
        db,
        email=configured_email or _LOCAL_FALLBACK_EMAIL,
        password=f"local-{uuid4().hex}-{uuid4().hex}",
    )


def build_remote_source_metadata(source: RemoteCommandSource | None) -> dict[str, str]:
    info = source or RemoteCommandSource()
    out: dict[str, str] = {}
    for key, raw in (
        ("source_user_name", info.user_name),
        ("source_open_id", info.open_id),
        ("source_chat_id", info.chat_id),
        ("source_message_id", info.message_id),
    ):
        text = str(raw or "").strip()
        if text:
            out[key] = text[:240]
    return out


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_remote_text(value: str) -> str:
    return " ".join(str(value or "").replace("\u3000", " ").strip().split())


def _known_remote_command_prefixes() -> list[str]:
    raw_prefixes = [
        "/aelin",
        str(getattr(settings, "feishu_bot_command_prefix", "") or ""),
        str(getattr(settings, "qq_bot_command_prefix", "") or ""),
    ]
    out: list[str] = []
    for raw in raw_prefixes:
        clean = _normalize_remote_text(raw).casefold()
        if clean and clean not in out:
            out.append(clean)
    return out


def _strip_remote_command_prefix(value: str) -> str:
    text = _normalize_remote_text(value)
    if not text:
        return ""
    folded = text.casefold()
    for prefix in _known_remote_command_prefixes():
        if folded == prefix:
            return ""
        if folded.startswith(prefix):
            remainder = text[len(prefix) :].strip()
            if remainder:
                return remainder
    return text


def _normalize_route_suffix(value: str) -> str | None:
    clean = _normalize_remote_text(value)
    if not clean:
        return "/"
    if clean.startswith("/"):
        return clean.split()[0][:120]
    alias = _AELIN_ROUTE_ALIASES.get(clean.casefold())
    if alias:
        return alias
    return None


def _parse_remote_command(text: str) -> ParsedRemoteCommand | None:
    normalized = _strip_remote_command_prefix(text)
    if not normalized:
        return None

    if _REMOTE_STATUS_RE.fullmatch(normalized):
        return ParsedRemoteCommand(kind="device", args={"action": "status"})

    if _REMOTE_SCREENSHOT_RE.fullmatch(normalized):
        return ParsedRemoteCommand(kind="screen_get", args={})

    open_aelin_match = _REMOTE_OPEN_AELIN_RE.fullmatch(normalized)
    if open_aelin_match is not None:
        suffix = str(
            open_aelin_match.group("suffix")
            or open_aelin_match.group("suffix_cn")
            or ""
        ).strip()
        route = _normalize_route_suffix(suffix)
        if route is not None:
            return ParsedRemoteCommand(
                kind="device",
                args={"action": "open_aelin", "route": route},
            )

    url_match = _REMOTE_URL_RE.search(normalized)
    if url_match is not None:
        url = str(url_match.group(0) or "").rstrip(".,!?)]}>")
        folded = normalized.casefold()
        open_keywords = (
            "open ",
            "visit ",
            "browse ",
            "url ",
            "\u6253\u5f00",
            "\u8bbf\u95ee",
            "\u94fe\u63a5",
            "\u7f51\u5740",
        )
        if normalized == url or any(keyword in folded for keyword in open_keywords):
            return ParsedRemoteCommand(
                kind="device",
                args={"action": "open_url", "url": url},
            )
    return None


def _build_remote_response(
    answer: str,
    *,
    actions: list[ChatAction] | None = None,
) -> ChatResponse:
    return ChatResponse(
        answer=str(answer or "").strip(),
        citations=[],
        actions=list(actions or []),
        memory_summary="",
        generated_at=_now_utc(),
    )


def _build_status_answer(result: dict[str, Any]) -> str:
    platform_name = str(result.get("platform") or "unknown")
    reachable = bool(result.get("desktop_plugin_reachable"))
    capabilities = dict(result.get("capabilities") or {})
    available_actions: list[str] = []
    if bool(capabilities.get("desktop_open_url")):
        available_actions.append("\u6253\u5f00\u7f51\u5740")
    if bool(capabilities.get("desktop_activate_module")):
        available_actions.append("\u6253\u5f00 Aelin")
    if bool(capabilities.get("desktop_execute_command")):
        available_actions.append("\u6267\u884c\u547d\u4ee4")
    available_text = "\u3001".join(available_actions) if available_actions else "\u65e0"
    notes = [str(item or "").strip() for item in list(result.get("notes") or []) if str(item or "").strip()]
    note_text = f"\u3002\u5907\u6ce8\uff1a{'; '.join(notes)}" if notes else ""
    return (
        f"\u5f53\u524d\u8bbe\u5907\u72b6\u6001\uff1aplatform={platform_name}\uff0c"
        f"\u684c\u9762\u63d2\u4ef6{'\u5df2\u8fde\u63a5' if reachable else '\u672a\u8fde\u63a5'}\uff0c"
        f"\u53ef\u7528\u80fd\u529b\uff1a{available_text}"
        f"{note_text}"
    )


def _build_direct_command_result(
    command: ParsedRemoteCommand,
    raw_result: dict[str, Any],
) -> RemoteControlExecutionResult:
    ok = bool(raw_result.get("ok"))
    if command.kind == "screen_get":
        if ok:
            width = max(0, int(raw_result.get("width") or 0))
            height = max(0, int(raw_result.get("height") or 0))
            answer = (
                f"\u5df2\u5b8c\u6210\u622a\u56fe\u3002"
                f"\u56fe\u50cf\u5c3a\u5bf8\uff1a{width}x{height}\u3002"
            )
            response = _build_remote_response(
                answer,
                actions=[
                    ChatAction(
                        kind="remote_screen_capture",
                        title="\u5df2\u5b8c\u6210\u622a\u56fe",
                        detail=f"{width}x{height}",
                        payload={
                            "name": str(raw_result.get("name") or ""),
                            "source_display": str(raw_result.get("source_display") or ""),
                        },
                    )
                ],
            )
            return RemoteControlExecutionResult(ok=True, status="completed", response=response)
        error = str(raw_result.get("error") or "screen_get_failed")
        response = _build_remote_response(
            f"\u622a\u56fe\u5931\u8d25\uff1a{error}"
        )
        return RemoteControlExecutionResult(ok=False, status="screen_capture_failed", response=response)

    action = str(command.args.get("action") or "").strip().lower()
    if ok and action == "status":
        return RemoteControlExecutionResult(
            ok=True,
            status="completed",
            response=_build_remote_response(_build_status_answer(raw_result)),
        )
    if ok and action == "open_url":
        url = str(raw_result.get("url") or command.args.get("url") or "").strip()
        return RemoteControlExecutionResult(
            ok=True,
            status="completed",
            response=_build_remote_response(
                f"\u5df2\u5c1d\u8bd5\u5728\u672c\u673a\u6d4f\u89c8\u5668\u6253\u5f00\u7f51\u5740\uff1a{url}",
                actions=[
                    ChatAction(
                        kind="remote_open_url",
                        title="\u5df2\u6253\u5f00\u7f51\u5740",
                        detail=url,
                        payload={"url": url},
                    )
                ],
            ),
        )
    if ok and action == "open_aelin":
        route = str(raw_result.get("route") or command.args.get("route") or "/").strip() or "/"
        detail = route if route != "/" else "\u4e3b\u754c\u9762"
        return RemoteControlExecutionResult(
            ok=True,
            status="completed",
            response=_build_remote_response(
                (
                    "\u5df2\u5c1d\u8bd5\u5524\u8d77 Aelin \u7a97\u53e3\u3002"
                    if route == "/"
                    else f"\u5df2\u5c1d\u8bd5\u6253\u5f00 Aelin\uff1a{route}"
                ),
                actions=[
                    ChatAction(
                        kind="remote_open_aelin",
                        title="\u5df2\u6253\u5f00 Aelin",
                        detail=detail,
                        payload={"route": route},
                    )
                ],
            ),
        )

    error = str(raw_result.get("error") or "device_action_failed")
    failure_label = {
        "status": "\u83b7\u53d6\u8bbe\u5907\u72b6\u6001",
        "open_url": "\u6253\u5f00\u7f51\u5740",
        "open_aelin": "\u6253\u5f00 Aelin",
    }.get(action, "\u6267\u884c\u8fdc\u7a0b\u63a7\u5236")
    return RemoteControlExecutionResult(
        ok=False,
        status="device_action_failed",
        response=_build_remote_response(f"{failure_label}\u5931\u8d25\uff1a{error}"),
    )


def _execute_direct_remote_command(payload: RemoteControlExecuteRequest) -> RemoteControlExecutionResult | None:
    command = _parse_remote_command(str(payload.text or ""))
    if command is None:
        return None
    if command.kind == "screen_get":
        raw_result = device_actions.screen_get_result(command.args)
    else:
        raw_result = device_actions.run_device_action(command.args)
    return _build_direct_command_result(command, raw_result)


def _normalized_remote_query(text: str) -> str:
    normalized = _strip_remote_command_prefix(text)
    return normalized or _normalize_remote_text(text)


def build_remote_chat_request(
    payload: RemoteControlExecuteRequest,
    *,
    source: RemoteCommandSource | None = None,
) -> ChatRequest:
    metadata = build_remote_source_metadata(source)
    return ChatRequest(
        query=_normalized_remote_query(str(payload.text or "")),
        workspace=str(payload.workspace or "default").strip() or "default",
        source=str((source.source if source is not None else payload.source) or "remote_control").strip().lower()[:32]
        or "remote_control",
        source_metadata=metadata,
        history=list(payload.history or []),
        images=list(payload.images or []),
        attachment_ids=list(payload.attachment_ids or []),
    )


def build_remote_control_status() -> dict[str, Any]:
    tool_status = device_actions.device_status_result()
    return {
        "enabled": True,
        "source": "remote_control",
        "capabilities": dict(tool_status.get("capabilities") or {}),
        "notes": list(tool_status.get("notes") or []),
        "supported_tools": supported_deepagents_tools(tool_status),
        "supported_device_actions": list(SUPPORTED_DEVICE_ACTIONS),
        "desktop_plugin_reachable": bool(tool_status.get("desktop_plugin_reachable")),
        "generated_at": datetime.now(timezone.utc),
    }


def _derive_remote_execution_status(response: ChatResponse) -> tuple[bool, str]:
    answer = str(getattr(response, "answer", "") or "").strip()
    if is_deepagents_no_result_response(response):
        return False, "deepagents_no_result"
    if not answer:
        return False, "empty_answer"
    return True, "completed"


def execute_remote_control_request(
    db: Session,
    *,
    current_user: User,
    payload: RemoteControlExecuteRequest,
    source: RemoteCommandSource | None = None,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> RemoteControlExecutionResult:
    direct_result = _execute_direct_remote_command(payload)
    if direct_result is not None:
        return direct_result
    chat_payload = build_remote_chat_request(payload, source=source)
    response = run_chat_request(
        chat_payload,
        db,
        current_user,
        event_cb=event_cb,
        cancel_token=cancel_token,
    )
    ok, status = _derive_remote_execution_status(response)
    return RemoteControlExecutionResult(ok=ok, status=status, response=response)
