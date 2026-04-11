from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AttachmentDocument, User
from app.routers.auth import get_current_user
from app.schemas import (
    AelinAttachmentUploadResponse,
    AelinFileMemoryContentResponse,
    AelinFileMemorySearchResponse,
)
from app.services.attachments.attachment_service import AttachmentIngestError, get_attachment_service
from app.services.memory.agent_memory import get_agent_memory_service
from app.services.memory.file_memory_bridge import file_memory_bridge

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("/upload", response_model=AelinAttachmentUploadResponse)
def upload_attachment(
    file: UploadFile = File(...),
    workspace: str = Form(default="default"),
    session_id: str = Form(default=""),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = get_attachment_service()
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


@router.get("/file-memory/search", response_model=AelinFileMemorySearchResponse)
def file_memory_search(
    workspace: str = "default",
    query: str = "",
    top_k: int = 6,
    kinds: str = "",
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AelinFileMemorySearchResponse:
    _ = db
    workspace_norm = str(workspace or "default").strip() or "default"
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return AelinFileMemorySearchResponse(
            workspace=workspace_norm,
            total=0,
            items=[],
            generated_at=datetime.now(timezone.utc),
        )
    items = get_agent_memory_service().search_memory(
        user_id=int(current_user.id),
        workspace=workspace_norm,
        query=normalized_query,
        top_k=max(1, min(20, int(top_k or 6))),
        kinds=[part.strip() for part in str(kinds or "").split(",") if part.strip()],
    )
    return AelinFileMemorySearchResponse(
        workspace=workspace_norm,
        total=len(items),
        items=items,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/file-memory/content", response_model=AelinFileMemoryContentResponse)
def file_memory_content(
    workspace: str = "default",
    path: str = "",
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AelinFileMemoryContentResponse:
    _ = db
    workspace_norm = str(workspace or "default").strip() or "default"
    entry = file_memory_bridge.read_memory_markdown(
        user_id=int(current_user.id),
        workspace=workspace_norm,
        path=path,
    )
    if not entry:
        raise HTTPException(status_code=404, detail="file_memory_entry_not_found")
    return AelinFileMemoryContentResponse(
        workspace=workspace_norm,
        path=str(path or "").strip(),
        title=str(entry.get("title") or ""),
        source=str(entry.get("source") or ""),
        kind=str(entry.get("kind") or ""),
        topic_path=str(entry.get("topic_path") or ""),
        entry_kind=str(entry.get("entry_kind") or ""),
        updated_at=str(entry.get("updated_at") or ""),
        content=str(entry.get("content") or ""),
        generated_at=datetime.now(timezone.utc),
    )
