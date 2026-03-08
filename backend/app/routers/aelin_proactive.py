from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AgentMemoryNote, Message, User
from app.routers.auth import get_current_user
from app.schemas import AelinNotificationItem, AelinProactivePollResponse
from app.services.aelin_runtime import normalize_workspace, parse_iso_datetime
from app.services.agent_memory import AgentMemoryService
from app.services.device_center import collect_device_process_items as device_collect_process_items

router = APIRouter(prefix="/aelin", tags=["aelin"])

_memory = AgentMemoryService()
_PROACTIVE_STATE_SOURCE_PREFIX = "proactive_state"
_PROACTIVE_SEEN_LIMIT = 180


def _proactive_state_source(workspace: str) -> str:
    workspace_norm = normalize_workspace(workspace)
    if workspace_norm == "default":
        return _PROACTIVE_STATE_SOURCE_PREFIX
    return f"{_PROACTIVE_STATE_SOURCE_PREFIX}:{workspace_norm}"


def _json_from_text(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_int_list(raw: Any, *, max_items: int = _PROACTIVE_SEEN_LIMIT) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    if not isinstance(raw, list):
        return out
    for item in raw:
        try:
            value = int(item)
        except Exception:
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= max_items:
            break
    return out


def _load_proactive_state(db: Session, *, user_id: int, workspace: str) -> tuple[AgentMemoryNote | None, dict[str, Any]]:
    source = _proactive_state_source(workspace)
    row = db.scalar(
        select(AgentMemoryNote)
        .where(AgentMemoryNote.user_id == user_id, AgentMemoryNote.source == source)
        .order_by(AgentMemoryNote.updated_at.desc(), AgentMemoryNote.id.desc())
        .limit(1)
    )
    if row is None:
        return None, {}
    return row, _json_from_text(row.content or "{}")


def _save_proactive_state(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    existing: AgentMemoryNote | None,
    state: dict[str, Any],
) -> AgentMemoryNote:
    source = _proactive_state_source(workspace)
    payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    row = existing
    if row is None:
        row = AgentMemoryNote(
            user_id=user_id,
            kind="system",
            source=source,
            content=payload,
        )
        db.add(row)
        return row
    row.kind = "system"
    row.source = source
    row.content = payload
    db.add(row)
    return row


@router.get("/proactive/poll", response_model=AelinProactivePollResponse)
def poll_aelin_proactive_events(
    workspace: str = Query(default="default", min_length=1, max_length=64),
    limit: int = Query(default=8, ge=1, le=24),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    workspace_norm = normalize_workspace(workspace)
    max_items = max(1, min(24, int(limit or 8)))

    existing, state = _load_proactive_state(db, user_id=current_user.id, workspace=workspace_norm)
    initialized = bool(state.get("initialized"))
    seen_focus_ids = _safe_int_list(state.get("seen_focus_message_ids"), max_items=_PROACTIVE_SEEN_LIMIT)
    seen_focus_set = set(seen_focus_ids)

    events: list[dict[str, Any]] = []
    brief = _memory.build_daily_brief(db, current_user.id)
    top_updates = brief.get("top_updates") if isinstance(brief, dict) else []
    if not isinstance(top_updates, list):
        top_updates = []

    for row in top_updates[:10]:
        if not isinstance(row, dict):
            continue
        try:
            message_id = int(row.get("message_id") or 0)
        except Exception:
            message_id = 0
        if message_id <= 0:
            continue
        if message_id in seen_focus_set:
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        source_label = str(row.get("source_label") or row.get("source") or "来源")
        sender = str(row.get("sender") or "unknown")
        events.append(
            {
                "id": f"proactive-focus-{message_id}",
                "level": "info",
                "title": f"发现新动态: {title[:80]}",
                "detail": f"{source_label} · {sender}",
                "source": "proactive",
                "ts": now.isoformat(),
                "action_kind": "open_message",
                "action_payload": {"message_id": str(message_id)},
            }
        )
        seen_focus_set.add(message_id)
        if len(events) >= max_items:
            break


    unread_count = int(
        db.scalar(select(func.count(Message.id)).where(Message.user_id == current_user.id, Message.is_read.is_(False))) or 0
    )
    last_unread_count = int(state.get("last_unread_count") or 0)
    unread_alert_at = parse_iso_datetime(str(state.get("last_unread_alert_at") or ""))
    unread_alert_due = unread_alert_at is None or (now - unread_alert_at) >= timedelta(hours=2)
    unread_spike = unread_count >= 6 and (unread_count >= (last_unread_count + 3))
    if (unread_spike or (unread_count >= 10 and unread_alert_due)) and len(events) < max_items:
        events.append(
            {
                "id": f"proactive-unread-{now.strftime('%Y%m%d%H')}",
                "level": "warning",
                "title": "未读消息堆积提醒",
                "detail": f"当前有 {unread_count} 条未读，建议现在清理高价值更新。",
                "source": "proactive",
                "ts": now.isoformat(),
                "action_kind": "open_brief",
                "action_payload": {"path": "/"},
            }
        )
        state["last_unread_alert_at"] = now.isoformat()

    process_alert_at = parse_iso_datetime(str(state.get("last_process_alert_at") or ""))
    process_alert_due = process_alert_at is None or (now - process_alert_at) >= timedelta(minutes=40)
    process_alert_pid = int(state.get("last_process_alert_pid") or 0)
    process_rows = device_collect_process_items(sort_by="cpu", limit=6)
    top_process = process_rows[0] if process_rows else None
    if (
        top_process
        and top_process.anomaly_score >= 2.2
        and len(events) < max_items
        and (process_alert_due or int(top_process.pid) != process_alert_pid)
    ):
        reason = "；".join(top_process.anomaly_reasons[:2]) or "资源占用偏高"
        events.append(
            {
                "id": f"proactive-proc-{int(top_process.pid)}-{now.strftime('%Y%m%d%H%M')}",
                "level": "warning",
                "title": f"设备负载提醒: {top_process.name}",
                "detail": (
                    f"CPU {top_process.cpu_percent:.1f}% · 内存 {top_process.memory_mb:.0f}MB；{reason}"
                ),
                "source": "device",
                "ts": now.isoformat(),
                "action_kind": "open_device",
                "action_payload": {"pid": str(int(top_process.pid)), "view": "processes"},
            }
        )
        state["last_process_alert_at"] = now.isoformat()
        state["last_process_alert_pid"] = int(top_process.pid)

    if not initialized and not events and top_updates:
        row = top_updates[0] if isinstance(top_updates[0], dict) else {}
        title = str(row.get("title") or "").strip()
        if title:
            events.append(
                {
                    "id": f"proactive-hello-{now.strftime('%Y%m%d%H%M')}",
                    "level": "info",
                    "title": "Aelin 已为你准备今日重点",
                    "detail": title[:120],
                    "source": "proactive",
                    "ts": now.isoformat(),
                    "action_kind": "open_brief",
                    "action_payload": {"path": "/"},
                }
            )

    if not initialized:
        events = events[:1]

    next_seen = [*seen_focus_set]
    next_seen.sort(reverse=True)
    next_state: dict[str, Any] = {
        "initialized": True,
        "workspace": workspace_norm,
        "seen_focus_message_ids": next_seen[:_PROACTIVE_SEEN_LIMIT],
        "last_unread_count": unread_count,
        "last_unread_alert_at": str(state.get("last_unread_alert_at") or ""),
        "last_process_alert_at": str(state.get("last_process_alert_at") or ""),
        "last_process_alert_pid": int(state.get("last_process_alert_pid") or 0),
        "last_poll_at": now.isoformat(),
    }
    _save_proactive_state(
        db,
        user_id=current_user.id,
        workspace=workspace_norm,
        existing=existing,
        state=next_state,
    )
    db.commit()

    items = [AelinNotificationItem(**item) for item in events[:max_items]]
    return AelinProactivePollResponse(
        workspace=workspace_norm,
        total=len(items),
        items=items,
        generated_at=now,
    )
