from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable

from app.db import create_session
from app.models import User
from app.schemas import AelinChatRequest, AelinChatResponse

_CHAT_WORKER_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="aelin-chat-worker")


def run_aelin_chat_with_local_session(
    payload: AelinChatRequest,
    *,
    user_id: int,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
) -> AelinChatResponse:
    from app.routers import aelin as aelin_router

    local_db = create_session()
    try:
        user = local_db.get(User, int(user_id))
        if user is None:
            raise RuntimeError("chat_worker_user_not_found")
        return aelin_router._dispatch_aelin_chat(payload, local_db, user, event_cb=event_cb)
    finally:
        try:
            local_db.close()
        except Exception:
            pass


def run_aelin_chat_in_worker_thread(
    payload: AelinChatRequest,
    *,
    user_id: int,
    timeout_seconds: float = 150.0,
) -> AelinChatResponse:
    future = _CHAT_WORKER_POOL.submit(
        run_aelin_chat_with_local_session,
        payload,
        user_id=int(user_id),
        event_cb=None,
    )
    try:
        return future.result(timeout=max(5.0, float(timeout_seconds or 150.0)))
    except FutureTimeoutError as exc:
        future.cancel()
        raise RuntimeError("aelin_chat_worker_timeout") from exc
