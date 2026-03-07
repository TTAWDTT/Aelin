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
from app.services.browser_plane import browser_plane_adapter
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
    login_rows = browser_plane_adapter.list_login_states(
        user_id=int(current_user.id),
        statuses=["awaiting_login", "continue_failed"],
        limit=limit,
    )
    login_items = [
        AelinNotificationItem(
            id=f"browser_login:{str(row.get('request_id') or '')}",
            level="warning" if str(row.get("status") or "") == "continue_failed" else "info",
            title="浏览器登录后可继续任务",
            detail=f"{str(row.get('domain') or '受控浏览器')} 登录完成后，可恢复之前的自动任务。",
            source="browser_login",
            ts=str(row.get("updated_at") or row.get("created_at") or ""),
            action_kind="confirm_browser_action",
            action_payload={
                "workspace": str(row.get("workspace") or "default"),
                "login_request_id": str(row.get("request_id") or ""),
                "profile_id": str(row.get("profile_id") or ""),
                "resume_query": str(row.get("resume_query") or ""),
                "continue_after_confirm": "true" if bool(row.get("continue_after_confirm", True)) else "false",
                "resume_request": json.dumps(row.get("resume_request") or {}, ensure_ascii=False, separators=(",", ":")),
                "next_call": json.dumps(row.get("next_call") or {}, ensure_ascii=False, separators=(",", ":")),
            },
        )
        for row in login_rows
        if str(row.get("request_id") or "").strip()
    ]

    merged: list[AelinNotificationItem] = []
    seen_ids: set[str] = set()
    for row in [*login_items, *tracking_items, *memory_items]:
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
