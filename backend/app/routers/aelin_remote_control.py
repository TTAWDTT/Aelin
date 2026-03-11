from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import (
    RemoteControlExecuteRequest,
    RemoteControlExecuteResponse,
    RemoteControlStatusResponse,
)
from app.services.remote_control import (
    RemoteCommandSource,
    build_remote_control_status,
    execute_remote_control_request,
)

router = APIRouter(prefix="/aelin/remote-control", tags=["aelin"])


@router.get("/status", response_model=RemoteControlStatusResponse)
def get_remote_control_status(
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return RemoteControlStatusResponse(**build_remote_control_status())


@router.post("/execute", response_model=RemoteControlExecuteResponse)
def execute_remote_control(
    payload: RemoteControlExecuteRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    response = execute_remote_control_request(
        db,
        current_user=current_user,
        payload=payload,
        source=RemoteCommandSource(
            source=str(payload.source or "manual_remote"),
            user_name=str(payload.source_user_name or current_user.email),
            open_id=str(payload.source_open_id or ""),
            chat_id=str(payload.source_chat_id or ""),
            message_id=str(payload.source_message_id or ""),
        ),
    )
    return RemoteControlExecuteResponse(
        ok=bool(str(response.answer or "").strip()),
        source="remote_control",
        response=response,
        generated_at=datetime.now(timezone.utc),
    )
