from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.models import User
from app.schemas import ChatRequest, ChatResponse, RemoteControlExecuteRequest
from app.services.aelin.core import is_deepagents_no_result_response, run_chat_request
from app.services.device import device_actions
from app.services.device.device_contract import (
    SUPPORTED_DEEPAGENTS_TOOLS,
    SUPPORTED_DEVICE_ACTIONS,
)
from app.settings import settings


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
) -> ChatRequest:
    metadata = build_remote_source_metadata(source)
    return ChatRequest(
        query=str(payload.text or "").strip(),
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
        "supported_tools": list(SUPPORTED_DEEPAGENTS_TOOLS),
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

