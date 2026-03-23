from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.models import User
from app.schemas import AelinChatRequest, AelinChatResponse, AelinToolStep, RemoteControlExecuteRequest
from app.services.aelin.chat_dispatch import dispatch_aelin_chat
from app.services.aelin.core import _try_agent_loop_chat
from app.services.aelin.expressions import _pick_expression
from app.services.aelin.streaming import _now_ms
from app.services.device.device_center import device_status_snapshot
from app.settings import settings

_SUPPORTED_TOOLS = [
    "device",
    "screen_get",
]

_SUPPORTED_DEVICE_ACTIONS = [
    "status",
    "open_url",
    "open_aelin",
]


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
    response: AelinChatResponse


def resolve_remote_control_user(db: Session, *, bind_user_email: str | None = None) -> User:
    raw_email = getattr(settings, "feishu_bot_bind_user_email", "") if bind_user_email is None else bind_user_email
    configured_email = str(raw_email or "").strip().lower()
    if configured_email:
        bound = db.scalar(select(User).where(User.email == configured_email))
        if bound is not None:
            return bound
    user = db.scalar(select(User).order_by(User.id.asc()))
    if user is not None:
        return user
    return crud.create_user(
        db,
        email=configured_email or "local@aelin.local",
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


def build_remote_chat_request(
    payload: RemoteControlExecuteRequest,
    *,
    source: RemoteCommandSource | None = None,
) -> AelinChatRequest:
    metadata = build_remote_source_metadata(source)
    return AelinChatRequest(
        query=str(payload.text or "").strip(),
        workspace=str(payload.workspace or "default").strip() or "default",
        source=str((source.source if source is not None else payload.source) or "remote_control").strip().lower()[:32]
        or "remote_control",
        source_metadata=metadata,
        history=list(payload.history or []),
        images=list(payload.images or []),
        attachment_ids=list(payload.attachment_ids or []),
        search_mode=str(payload.search_mode or "auto").strip() or "auto",
    )


def build_remote_control_status() -> dict[str, Any]:
    snapshot = device_status_snapshot()
    return {
        "enabled": True,
        "source": "remote_control",
        "capabilities": dict(snapshot.get("capabilities") or {}),
        "notes": list(snapshot.get("notes") or []),
        "supported_tools": list(_SUPPORTED_TOOLS),
        "supported_device_actions": list(_SUPPORTED_DEVICE_ACTIONS),
        "desktop_plugin_reachable": bool(snapshot.get("desktop_plugin_reachable")),
        "generated_at": datetime.now(timezone.utc),
    }


def _derive_remote_execution_status(response: AelinChatResponse) -> tuple[bool, str]:
    answer = str(getattr(response, "answer", "") or "").strip()
    trace = list(getattr(response, "tool_trace", []) or [])
    fallback_failed = any(
        str(getattr(step, "stage", "") or "") == "agent_loop"
        and str(getattr(step, "status", "") or "") == "failed"
        and "agent_loop_no_result" in str(getattr(step, "detail", "") or "")
        for step in trace
        if isinstance(step, AelinToolStep)
    )
    if fallback_failed:
        return False, "agent_loop_no_result"
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
    chat_payload = build_remote_chat_request(payload, source=source)
    response = dispatch_aelin_chat(
        chat_payload,
        db,
        current_user,
        event_cb=event_cb,
        cancel_token=cancel_token,
        try_agent_loop_chat=_try_agent_loop_chat,
        pick_expression=_pick_expression,
        now_ms=_now_ms,
    )
    ok, status = _derive_remote_execution_status(response)
    return RemoteControlExecutionResult(ok=ok, status=status, response=response)

