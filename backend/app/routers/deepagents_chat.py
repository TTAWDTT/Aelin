from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.models import User
from app.routers.auth import get_current_user
from app.services.deepagents.stream_gateway import build_deepagents_stream_response


router = APIRouter(prefix="/deepagents", tags=["deepagents"])


@router.post("/chat/stream")
def deepagents_chat_stream(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    return build_deepagents_stream_response(
        payload,
        current_user=current_user,
    )
