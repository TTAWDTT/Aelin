from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import AelinNotificationItem, AelinNotificationResponse
from app.services.agent_memory import AgentMemoryService
from app.services.tracking_autonomy import tracking_autonomy_service

router = APIRouter(prefix="/aelin", tags=["aelin"])

_memory = AgentMemoryService()
_tracking = tracking_autonomy_service


@router.get("/notifications", response_model=AelinNotificationResponse)
def list_aelin_notifications(
    limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    memory_items = [AelinNotificationItem(**item) for item in _memory.build_notifications(db, current_user.id, limit=limit)]
    tracking_rows, to_mark = _tracking.build_notification_items(db, user_id=current_user.id, limit=limit)
    tracking_items = [AelinNotificationItem(**item) for item in tracking_rows]

    merged: list[AelinNotificationItem] = []
    seen_ids: set[str] = set()
    for row in [*tracking_items, *memory_items]:
        key = str(row.id or "").strip()
        if not key or key in seen_ids:
            continue
        seen_ids.add(key)
        merged.append(row)
        if len(merged) >= limit:
            break

    if to_mark:
        _tracking.mark_notified(db, change_ids=to_mark)
        db.commit()

    return AelinNotificationResponse(
        total=len(merged),
        items=merged,
        generated_at=datetime.now(timezone.utc),
    )
