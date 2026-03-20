from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.routers.aelin import _build_cached_base_context_bundle, _build_context_bundle
from app.routers.auth import get_current_user
from app.schemas import AelinContextResponse

router = APIRouter(prefix="/aelin", tags=["aelin"])


@router.get("/context", response_model=AelinContextResponse)
def get_aelin_context(
    workspace: str = Query(default="default", min_length=1, max_length=64),
    query: str = Query(default="", max_length=400),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not (query or "").strip():
        bundle = _build_cached_base_context_bundle(
            db,
            current_user.id,
            workspace=workspace,
        )
    else:
        bundle = _build_context_bundle(
            db,
            current_user.id,
            workspace=workspace,
            query=query,
        )
    return AelinContextResponse(
        workspace=bundle["workspace"],
        summary=bundle["summary"],
        notes=bundle["notes"],
        notes_count=bundle["notes_count"],
        todos=bundle["todos"],
        memory_layers=bundle["memory_layers"],
        generated_at=datetime.now(timezone.utc),
    )
