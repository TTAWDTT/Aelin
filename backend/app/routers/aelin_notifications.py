from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import AelinNotificationItem, AelinNotificationResponse
from app.services.agent_memory import AgentMemoryService

router = APIRouter(prefix="/aelin", tags=["aelin"])

_memory = AgentMemoryService()


@router.get("/notifications", response_model=AelinNotificationResponse)
def list_aelin_notifications(
    limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    memory_items = [AelinNotificationItem(**item) for item in _memory.build_notifications(db, current_user.id, limit=limit)]
    merged: list[AelinNotificationItem] = []
    seen_ids: set[str] = set()
    for row in memory_items:
        key = str(row.id or "").strip()
        if not key or key in seen_ids:
            continue
        seen_ids.add(key)
        merged.append(row)
        if len(merged) >= limit:
            break

    return AelinNotificationResponse(
        total=len(merged),
        items=merged,
        generated_at=datetime.now(timezone.utc),
    )
