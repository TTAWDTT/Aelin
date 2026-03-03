from __future__ import annotations

import queue
import threading
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import create_session, get_session
from app.models import User
from app.routers.aelin import _dispatch_aelin_chat, _normalize_search_mode
from app.routers.aelin_text_helpers import _now_ms, _sse_event
from app.routers.auth import get_current_user
from app.schemas import AelinChatRequest, AelinChatResponse


router = APIRouter(prefix="/aelin", tags=["aelin"])


@router.post("/chat", response_model=AelinChatResponse)
def aelin_chat(
    payload: AelinChatRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return _dispatch_aelin_chat(payload, db, current_user)


@router.post("/chat/stream")
def aelin_chat_stream(
    payload: AelinChatRequest,
    current_user: User = Depends(get_current_user),
):
    def _event_iter():
        event_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        done_token = "__done__"

        def _push(event: str, data: dict[str, Any]) -> None:
            event_queue.put((event, data))

        def _worker() -> None:
            local_db = create_session()
            try:
                user = local_db.get(User, int(current_user.id)) or current_user
                result = _dispatch_aelin_chat(payload, local_db, user, event_cb=_push)
                _push("final", {"result": result.model_dump()})
            except Exception as e:
                _push("error", {"message": str(e)[:500] or "stream error"})
            finally:
                try:
                    local_db.close()
                except Exception:
                    pass
                _push("done", {"ts": _now_ms(), "status": done_token})

        _push(
            "start",
            {
                "ts": _now_ms(),
                "query": payload.query.strip()[:180],
                "workspace": payload.workspace,
                "search_mode": _normalize_search_mode(getattr(payload, "search_mode", "auto")),
            },
        )
        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()

        while True:
            event, data = event_queue.get()
            yield _sse_event(event, data)
            if event == "done":
                break

    return StreamingResponse(_event_iter(), media_type="text/event-stream")
