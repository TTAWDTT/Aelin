from __future__ import annotations

from datetime import datetime, timezone
import logging
import queue
import threading
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import create_session, get_session
from app.models import AttachmentDocument, User
from app.routers.aelin import _dispatch_aelin_chat, _normalize_search_mode
from app.routers.aelin_text_helpers import _now_ms, _sse_event
from app.routers.auth import get_current_user
from app.schemas import (
    AelinAttachmentUploadResponse,
    AelinBrowserConfirmRequest,
    AelinBrowserConfirmResponse,
    AelinBrowserLoginCheckpointItem,
    AelinBrowserLoginCheckpointListResponse,
    AelinChatRequest,
    AelinChatResponse,
)
from app.services.aelin_attachment_service import AttachmentIngestError, get_aelin_attachment_service
from app.services.aelin_browser_confirm import confirm_browser_action_request, execute_confirmed_browser_call
from app.services.browser_automation import browser_automation_service


router = APIRouter(prefix="/aelin", tags=["aelin"])
_LOG = logging.getLogger(__name__)
_execute_confirmed_browser_call = execute_confirmed_browser_call


def _preview(text: str, *, limit: int = 180) -> str:
    raw = " ".join(str(text or "").split())
    if len(raw) <= limit:
        return raw
    return f"{raw[: max(0, limit - 1)]}…"


@router.post("/attachments/upload", response_model=AelinAttachmentUploadResponse)
def aelin_attachment_upload(
    file: UploadFile = File(...),
    workspace: str = Form(default="default"),
    session_id: str = Form(default=""),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = get_aelin_attachment_service()
    workspace_norm = service.normalize_workspace(workspace)
    session_norm = service.normalize_session(session_id)
    if session_norm:
        existing_workspace = db.scalar(
            select(AttachmentDocument.workspace)
            .where(
                AttachmentDocument.user_id == int(current_user.id),
                AttachmentDocument.session_id == session_norm,
            )
            .order_by(AttachmentDocument.id.desc())
        )
        if existing_workspace:
            workspace_norm = str(existing_workspace)

    max_size = int(service.max_size_bytes)
    if int(getattr(file, "size", 0) or 0) > max_size:
        try:
            file.file.close()
        except Exception:
            pass
        raise HTTPException(status_code=422, detail=f"附件过大（>{max_size} 字节）")

    content_buffer = bytearray()
    while True:
        piece = file.file.read(1024 * 1024)
        if not piece:
            break
        content_buffer.extend(piece)
        if len(content_buffer) > max_size:
            try:
                file.file.close()
            except Exception:
                pass
            raise HTTPException(status_code=422, detail=f"附件过大（>{max_size} 字节）")
    content = bytes(content_buffer)
    del content_buffer

    try:
        result = service.ingest_bytes(
            db,
            user_id=int(current_user.id),
            workspace=workspace_norm,
            session_id=session_norm,
            file_name=str(file.filename or "attachment"),
            mime_type=str(file.content_type or ""),
            content=content,
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
    except AttachmentIngestError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"附件处理失败: {str(exc)[:160]}") from exc
    finally:
        try:
            file.file.close()
        except Exception:
            pass
    response_payload = {key: value for key, value in result.items() if not str(key).startswith("_")}
    return AelinAttachmentUploadResponse(**response_payload)


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
        req_id = uuid4().hex[:10]
        started = _now_ms()
        heartbeat_count = 0
        event_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        done_token = "__done__"

        def _push(event: str, data: dict[str, Any]) -> None:
            _LOG.debug(
                "aelin_stream event req=%s uid=%s event=%s keys=%s",
                req_id,
                int(current_user.id),
                str(event),
                ",".join(sorted([str(k) for k in list((data or {}).keys())[:8] if str(k)])) or "-",
            )
            event_queue.put((event, data))

        def _worker() -> None:
            local_db = create_session()
            try:
                _LOG.info(
                    "aelin_stream worker_start req=%s uid=%s workspace=%s query=%s",
                    req_id,
                    int(current_user.id),
                    str(payload.workspace or "default")[:64],
                    _preview(str(payload.query or "")),
                )
                user = local_db.get(User, int(current_user.id)) or current_user
                result = _dispatch_aelin_chat(payload, local_db, user, event_cb=_push)
                _LOG.info(
                    "aelin_stream worker_final req=%s uid=%s answer_len=%s actions=%s traces=%s",
                    req_id,
                    int(current_user.id),
                    len(str(result.answer or "")),
                    len(list(result.actions or [])),
                    len(list(result.tool_trace or [])),
                )
                _push("final", {"result": result.model_dump()})
            except Exception as e:
                _LOG.exception(
                    "aelin_stream worker_error req=%s uid=%s error=%s",
                    req_id,
                    int(current_user.id),
                    str(e)[:220],
                )
                _push("error", {"message": str(e)[:500] or "stream error"})
            finally:
                try:
                    local_db.close()
                except Exception:
                    pass
                _push("done", {"ts": _now_ms(), "status": done_token})
                _LOG.info(
                    "aelin_stream worker_done req=%s uid=%s duration_ms=%s",
                    req_id,
                    int(current_user.id),
                    max(0, _now_ms() - started),
                )

        _push(
            "start",
            {
                "ts": _now_ms(),
                "req_id": req_id,
                "query": payload.query.strip()[:180],
                "workspace": payload.workspace,
                "search_mode": _normalize_search_mode(getattr(payload, "search_mode", "auto")),
            },
        )
        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()

        heartbeat_interval_s = 5.0
        try:
            while True:
                try:
                    event, data = event_queue.get(timeout=heartbeat_interval_s)
                except queue.Empty:
                    # Emit a real SSE event so proxies/clients don't treat this as idle.
                    heartbeat_count += 1
                    yield _sse_event("ping", {"ts": _now_ms(), "req_id": req_id, "hb": heartbeat_count})
                    if (not worker.is_alive()) and event_queue.empty():
                        yield _sse_event("done", {"ts": _now_ms(), "status": done_token})
                        break
                    continue

                yield _sse_event(event, data)
                if event == "done":
                    break
        except BaseException as exc:
            _LOG.warning(
                "aelin_stream interrupted req=%s uid=%s type=%s msg=%s",
                req_id,
                int(current_user.id),
                type(exc).__name__,
                str(exc)[:180],
            )
            raise
        finally:
            _LOG.info(
                "aelin_stream closed req=%s uid=%s duration_ms=%s heartbeats=%s",
                req_id,
                int(current_user.id),
                max(0, _now_ms() - started),
                heartbeat_count,
            )

    return StreamingResponse(
        _event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/agent/browser/confirm", response_model=AelinBrowserConfirmResponse)
def confirm_browser_action(
    payload: AelinBrowserConfirmRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return confirm_browser_action_request(payload=payload, db=db, current_user=current_user)


@router.get("/agent/browser/login-checkpoints", response_model=AelinBrowserLoginCheckpointListResponse)
def list_browser_login_checkpoints(
    workspace: str = "default",
    status: str = "awaiting_login,continue_failed",
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    normalized_workspace = str(workspace or "").strip()[:64] or "default"
    statuses = [str(item).strip().lower() for item in str(status or "").split(",") if str(item).strip()]
    items = browser_automation_service.list_login_states(
        user_id=int(current_user.id),
        workspace=normalized_workspace,
        statuses=statuses,
        limit=max(1, min(100, int(limit or 20))),
    )
    return AelinBrowserLoginCheckpointListResponse(
        total=len(items),
        items=[AelinBrowserLoginCheckpointItem(**item) for item in items],
        generated_at=datetime.now(timezone.utc),
    )
