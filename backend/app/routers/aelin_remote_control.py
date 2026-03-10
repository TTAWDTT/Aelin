from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import (
    RemoteControlCommandListResponse,
    RemoteControlExecuteRequest,
    RemoteControlExecuteResponse,
    RemoteControlStatusResponse,
)
from app.services.device_center import desktop_plugin_health
from app.services.feishu_bot import feishu_bot_service
from app.services.remote_control import (
    RemoteCommandSource,
    build_remote_command_item,
    execute_remote_command,
    list_remote_commands,
    supported_commands,
)
from app.settings import settings

router = APIRouter(prefix="/aelin/remote-control", tags=["aelin"])


@router.get("/status", response_model=RemoteControlStatusResponse)
def get_remote_control_status(
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    snapshot = feishu_bot_service.snapshot()
    return RemoteControlStatusResponse(
        enabled=bool(snapshot.get("enabled", False)),
        running=bool(snapshot.get("running", False)),
        configured=bool(snapshot.get("configured", False)),
        sdk_available=bool(snapshot.get("sdk_available", False)),
        workspace=str(getattr(settings, "feishu_bot_workspace", "default") or "default"),
        bound_user_email=str(getattr(settings, "feishu_bot_bind_user_email", "") or ""),
        plugin_base_url=str(getattr(settings, "desktop_plugin_base_url", "") or ""),
        plugin_reachable=desktop_plugin_health(),
        commands=supported_commands(),
        last_error=str(snapshot.get("last_error") or ""),
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/commands", response_model=RemoteControlCommandListResponse)
def get_remote_control_commands(
    workspace: str = Query(default="default", min_length=1, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = list_remote_commands(db, user_id=current_user.id, workspace=workspace, limit=limit)
    return RemoteControlCommandListResponse(
        total=len(rows),
        items=[build_remote_command_item(row) for row in rows],
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/execute", response_model=RemoteControlExecuteResponse)
def execute_remote_control_command(
    payload: RemoteControlExecuteRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row, result = execute_remote_command(
        db,
        user=current_user,
        text=payload.text,
        workspace=payload.workspace,
        source=RemoteCommandSource(source="manual", user_name=current_user.email),
        prefix="",
        allow_without_prefix=True,
    )
    return RemoteControlExecuteResponse(
        ok=result.ok,
        reply_text=result.reply_text,
        item=build_remote_command_item(row),
        generated_at=datetime.now(timezone.utc),
    )

