from __future__ import annotations

from collections.abc import Callable
from sqlalchemy.orm import Session

from app.models import User
from app.schemas import ChatRequest, ChatResponse
import app.services.aelin.core as _core


router = _core.router


def run_chat_request(
    payload: ChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> ChatResponse:
    return _core.run_chat_request(payload, db, current_user, event_cb=event_cb, cancel_token=cancel_token)

