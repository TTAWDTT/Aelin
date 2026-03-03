from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import crud
from app.db import get_session
from app.models import Contact, Message, TrackingChange, TrackingTarget, User
from app.routers.auth import get_current_user
from app.schemas import (
    AelinAction,
    AelinDiaryTreeNode,
    AelinDiaryTreeResponse,
    AelinTrackConfirmRequest,
    AelinTrackConfirmResponse,
    AelinTrackingAckBatchRequest,
    AelinTrackingChangeItem,
    AelinTrackingChangeListResponse,
    AelinTrackingFileMemoryContentResponse,
    AelinTrackingFileMemoryItem,
    AelinTrackingFileMemorySearchResponse,
    AelinTrackingItem,
    AelinTrackingListResponse,
    AelinTrackingRunResponse,
    AelinTrackingSnapshotItem,
    AelinTrackingSnapshotListResponse,
    AelinTrackingTargetUpdateRequest,
)
from app.services import content_tagging
from app.services.agent_memory import AgentMemoryService
from app.services.openviking_bridge import tracking_file_memory_bridge
from app.services.aelin_runtime import json_from_text as _json_from_text
from app.services.aelin_runtime import normalize_workspace as _normalize_workspace
from app.services.aelin_runtime import parse_iso_datetime as _parse_iso_datetime
from app.services.aelin_tracking_events import infer_tracking_source as _infer_tracking_source
from app.services.aelin_tracking_events import normalize_track_source as _normalize_track_source
from app.services.tracking_autonomy import tracking_autonomy_service

router = APIRouter(prefix="/aelin", tags=["aelin"])

_memory = AgentMemoryService()
_tracking = tracking_autonomy_service
_tracking_file_memory = tracking_file_memory_bridge


def _target_to_tracking_item(row: TrackingTarget, *, unread_changes: int) -> AelinTrackingItem:
    cfg = _json_from_text(row.config_json or "{}")
    tags_raw = []
    try:
        parsed = json.loads(row.tags_json or "[]")
        if isinstance(parsed, list):
            tags_raw = [str(item).strip()[:32] for item in parsed if str(item).strip()]
    except Exception:
        tags_raw = []
    return AelinTrackingItem(
        note_id=None,
        message_id=None,
        target_id=int(row.id),
        target=(row.display_name or row.source_key or "").strip(),
        source=(row.source_type or "web").strip().lower() or "web",
        query=str(cfg.get("query") or "").strip(),
        workspace=row.workspace or "default",
        track_type=row.track_type or "term",
        description=(row.description or "").strip(),
        tags=tags_raw,
        status=row.status or "active",
        interval_seconds=max(30, int(row.interval_seconds or 120)),
        notify_level=row.notify_level or "all",
        unread_changes=max(0, int(unread_changes or 0)),
        error_count=max(0, int(row.error_count or 0)),
        next_run_at=row.next_run_at.isoformat() if row.next_run_at else None,
        last_run_at=row.last_run_at.isoformat() if row.last_run_at else None,
        last_checked_at=row.last_checked_at.isoformat() if row.last_checked_at else None,
        last_change_at=row.last_change_at.isoformat() if row.last_change_at else None,
        mute_until=row.mute_until.isoformat() if row.mute_until else None,
        is_temporary=bool(row.is_temporary),
        expires_at=row.expires_at.isoformat() if row.expires_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
        status_updated_at=(row.last_change_at.isoformat() if row.last_change_at else (row.updated_at.isoformat() if row.updated_at else None)),
    )


def _append_tracking_contact_event(
    db: Session,
    *,
    user_id: int,
    target: str,
    source: str,
    query: str,
    status: str,
) -> int | None:
    contact = crud.upsert_contact(db, user_id=user_id, handle="aelin:tracking", display_name="Aelin Tracking")
    now = datetime.now(timezone.utc)
    seed = f"{target}|{query}|{status}|{now.strftime('%Y%m%d%H%M%S')}"
    external_id = f"aelin-track:{source}:{hashlib.sha1(seed.encode('utf-8')).hexdigest()}"
    body = (
        f"跟踪目标: {target}\n"
        f"来源: {source}\n"
        f"状态: {status}\n"
        f"触发问题: {query or '未提供'}\n"
        f"时间: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    msg = crud.create_message(
        db,
        user_id=user_id,
        contact_id=contact.id,
        source="aelin",
        external_id=external_id,
        sender="Aelin",
        subject=f"跟踪任务：{target[:80]}",
        body=body,
        received_at=now,
        summary=f"{source} / {status}",
    )
    if msg is not None and getattr(msg, "id", None) is None:
        db.flush()
    if msg is None:
        msg = db.scalar(
            select(Message).where(
                Message.user_id == user_id,
                Message.source == "aelin",
                Message.external_id == external_id,
            )
        )
    if msg is None:
        return None
    crud.touch_contact_last_message(db, contact=contact, received_at=now)
    db.flush()
    return int(msg.id)


def _matching_accounts_for_tracking(accounts: list[Any], source: str) -> list[Any]:
    if source == "email":
        email_providers = {"imap", "gmail", "outlook", "forward"}
        return [a for a in accounts if str(getattr(a, "provider", "")).lower() in email_providers]
    return [a for a in accounts if str(getattr(a, "provider", "")).lower() == source]


@router.get("/tracking", response_model=AelinTrackingListResponse)
def list_trackings(
    limit: int = Query(default=80, ge=1, le=300),
    workspace: str = Query(default="", max_length=64),
    status: str = Query(default="", max_length=16),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    workspace_norm = _normalize_workspace(workspace) if (workspace or "").strip() else None
    _tracking.ensure_legacy_migration(db, user_id=current_user.id, workspace=workspace_norm or "default")
    rows = _tracking.list_targets(
        db,
        user_id=current_user.id,
        workspace=workspace_norm,
        status=(status or "").strip().lower() or None,
        limit=limit,
    )
    target_ids = [int(row.id) for row in rows if getattr(row, "id", None)]
    unread_counts: dict[int, int] = {}
    if target_ids:
        q = (
            select(TrackingChange.target_id, func.count(TrackingChange.id))
            .where(TrackingChange.target_id.in_(target_ids), TrackingChange.acked.is_(False))
            .group_by(TrackingChange.target_id)
        )
        unread_counts = {int(tid): int(cnt or 0) for tid, cnt in db.execute(q).all()}

    items = [_target_to_tracking_item(row, unread_changes=unread_counts.get(int(row.id), 0)) for row in rows]
    return AelinTrackingListResponse(
        total=len(items),
        items=items,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/tracking/targets", response_model=AelinTrackingListResponse)
def list_tracking_targets(
    limit: int = Query(default=80, ge=1, le=300),
    workspace: str = Query(default="", max_length=64),
    status: str = Query(default="", max_length=16),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return list_trackings(limit=limit, workspace=workspace, status=status, db=db, current_user=current_user)


@router.patch("/tracking/targets/{target_id}", response_model=AelinTrackingItem)
def update_tracking_target(
    target_id: int,
    payload: AelinTrackingTargetUpdateRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = _tracking.update_target(
        db,
        user_id=current_user.id,
        target_id=target_id,
        status=(payload.status or "").strip().lower() or None,
        interval_seconds=payload.interval_seconds,
        notify_level=payload.notify_level,
        mute_until=_parse_iso_datetime(payload.mute_until),
        description=payload.description,
        tags=payload.tags,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="tracking target not found")
    db.commit()
    unread = int(
        db.scalar(
            select(func.count(TrackingChange.id)).where(
                TrackingChange.target_id == int(row.id),
                TrackingChange.acked.is_(False),
            )
        )
        or 0
    )
    return _target_to_tracking_item(row, unread_changes=unread)


@router.post("/tracking/targets/{target_id}/run", response_model=AelinTrackingRunResponse)
def run_tracking_target(
    target_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = _tracking.run_target_now(user_id=current_user.id, target_id=target_id)
    return AelinTrackingRunResponse(
        ok=bool(result.get("ok")),
        message=str(result.get("message") or "run completed"),
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/tracking/targets/{target_id}/changes", response_model=AelinTrackingChangeListResponse)
def list_tracking_changes(
    target_id: int,
    limit: int = Query(default=80, ge=1, le=300),
    severity: str = Query(default="", max_length=16),
    change_type: str = Query(default="", max_length=32),
    acked: bool | None = Query(default=None),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = _tracking.list_changes(
        db,
        user_id=current_user.id,
        target_id=target_id,
        limit=limit,
        severity=(severity or "").strip().lower() or None,
        change_type=(change_type or "").strip().lower() or None,
        acked=acked,
    )
    items = [
        AelinTrackingChangeItem(
            id=int(row.id),
            target_id=int(row.target_id),
            change_type=row.change_type,
            severity=row.severity,
            title=row.title,
            summary=row.summary or "",
            diff_json=_json_from_text(row.diff_json or "{}"),
            dedupe_key=row.dedupe_key or "",
            notified=bool(row.notified),
            acked=bool(row.acked),
            created_at=row.created_at.isoformat() if row.created_at else "",
        )
        for row in rows
    ]
    return AelinTrackingChangeListResponse(total=len(items), items=items, generated_at=datetime.now(timezone.utc))


@router.post("/tracking/targets/{target_id}/changes/ack", response_model=AelinTrackingRunResponse)
def ack_tracking_changes_batch(
    target_id: int,
    payload: AelinTrackingAckBatchRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    target = db.get(TrackingTarget, int(target_id))
    if target is None or target.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="tracking target not found")

    change_ids = [int(cid) for cid in (payload.change_ids or []) if int(cid) > 0]
    if change_ids:
        id_set = set(change_ids)
        rows = db.scalars(
            select(TrackingChange.id).where(
                TrackingChange.target_id == int(target_id),
                TrackingChange.id.in_(id_set),
            )
        ).all()
        valid_ids = [int(cid) for cid in rows]
    else:
        rows = db.scalars(
            select(TrackingChange.id).where(
                TrackingChange.target_id == int(target_id),
                TrackingChange.acked.is_(False),
            )
        ).all()
        valid_ids = [int(cid) for cid in rows]

    acked_count = 0
    for change_id in valid_ids:
        row = _tracking.ack_change(db, user_id=current_user.id, change_id=change_id)
        if row is not None:
            acked_count += 1
    db.commit()
    return AelinTrackingRunResponse(
        ok=True,
        message=f"acked {acked_count}",
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/tracking/changes/{change_id}/ack", response_model=AelinTrackingRunResponse)
def ack_tracking_change(
    change_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = _tracking.ack_change(db, user_id=current_user.id, change_id=change_id)
    if row is None:
        raise HTTPException(status_code=404, detail="tracking change not found")
    db.commit()
    return AelinTrackingRunResponse(ok=True, message="acked", generated_at=datetime.now(timezone.utc))


@router.get("/tracking/targets/{target_id}/snapshots", response_model=AelinTrackingSnapshotListResponse)
def list_tracking_snapshots(
    target_id: int,
    limit: int = Query(default=80, ge=1, le=300),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = _tracking.list_snapshots(db, user_id=current_user.id, target_id=target_id, limit=limit)
    items = [
        AelinTrackingSnapshotItem(
            id=int(row.id),
            target_id=int(row.target_id),
            version_no=int(row.version_no),
            content_hash=row.content_hash or "",
            fetch_status=row.fetch_status or "ok",
            fetch_error=row.fetch_error or "",
            fetched_at=row.fetched_at.isoformat() if row.fetched_at else "",
            normalized_payload_json=_json_from_text(row.normalized_payload_json or "{}"),
        )
        for row in rows
    ]
    return AelinTrackingSnapshotListResponse(total=len(items), items=items, generated_at=datetime.now(timezone.utc))


@router.get("/tracking/file-memory/search", response_model=AelinTrackingFileMemorySearchResponse)
def search_tracking_file_memory(
    workspace: str = Query(default="default", min_length=1, max_length=64),
    query: str = Query(default="", max_length=500),
    limit: int = Query(default=12, ge=1, le=40),
    source: str = Query(default="", max_length=32),
    include_diary: bool = Query(default=True),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _tracking.ensure_legacy_migration(db, user_id=current_user.id, workspace=workspace)
    items_raw = _tracking_file_memory.search(
        user_id=current_user.id,
        workspace=workspace,
        query=query,
        limit=limit,
        source=(source or "").strip().lower() or None,
        include_diary=bool(include_diary),
    )
    items = [
        AelinTrackingFileMemoryItem(
            path=item.path,
            title=item.title,
            preview=item.preview,
            score=float(item.score),
            updated_at=item.updated_at,
            canonical_id=item.canonical_id,
            target=item.target,
            source=item.source,
            kind=item.kind,
            topic_path=item.topic_path,
            entry_kind=item.entry_kind,
        )
        for item in items_raw
    ]
    return AelinTrackingFileMemorySearchResponse(
        workspace=_normalize_workspace(workspace),
        total=len(items),
        items=items,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/tracking/file-memory/content", response_model=AelinTrackingFileMemoryContentResponse)
def get_tracking_file_memory_content(
    workspace: str = Query(default="default", min_length=1, max_length=64),
    path: str = Query(..., min_length=1, max_length=3000),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _tracking.ensure_legacy_migration(db, user_id=current_user.id, workspace=workspace)
    row = _tracking_file_memory.read_memory_markdown(
        user_id=current_user.id,
        workspace=workspace,
        path=path,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="memory file not found")
    return AelinTrackingFileMemoryContentResponse(
        workspace=_normalize_workspace(workspace),
        path=str(row.get("path") or ""),
        title=str(row.get("title") or ""),
        source=str(row.get("source") or ""),
        kind=str(row.get("kind") or ""),
        topic_path=str(row.get("topic_path") or ""),
        entry_kind=str(row.get("entry_kind") or ""),
        updated_at=str(row.get("updated_at") or ""),
        content=str(row.get("content") or ""),
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/tracking/file-memory/tree", response_model=AelinDiaryTreeResponse)
def list_tracking_diary_tree(
    workspace: str = Query(default="default", min_length=1, max_length=64),
    max_files: int = Query(default=500, ge=20, le=2000),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _tracking.ensure_legacy_migration(db, user_id=current_user.id, workspace=workspace)

    def _to_node(row: Any) -> AelinDiaryTreeNode:
        children_raw = getattr(row, "children", None)
        children = [
            _to_node(child)
            for child in (children_raw or [])
            if child is not None
        ]
        return AelinDiaryTreeNode(
            name=str(getattr(row, "name", "") or ""),
            path=str(getattr(row, "path", "") or ""),
            kind=str(getattr(row, "kind", "") or "file"),
            title=str(getattr(row, "title", "") or ""),
            preview=str(getattr(row, "preview", "") or ""),
            updated_at=str(getattr(row, "updated_at", "") or ""),
            source=str(getattr(row, "source", "") or ""),
            topic_path=str(getattr(row, "topic_path", "") or ""),
            entry_kind=str(getattr(row, "entry_kind", "") or ""),
            children=children,
        )

    items_raw = _tracking_file_memory.list_diary_tree(
        user_id=current_user.id,
        workspace=workspace,
        max_files=max_files,
    )
    items = [_to_node(row) for row in items_raw]

    def _count_files(nodes: list[AelinDiaryTreeNode]) -> int:
        total = 0
        for node in nodes:
            if node.kind == "file":
                total += 1
            if node.children:
                total += _count_files(node.children)
        return total

    return AelinDiaryTreeResponse(
        workspace=_normalize_workspace(workspace),
        total=_count_files(items),
        items=items,
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/track/confirm", response_model=AelinTrackConfirmResponse)
def confirm_track_subscription(
    payload: AelinTrackConfirmRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    target = payload.target.strip()[:240]
    query = (payload.query or "").strip()[:500]
    source = _normalize_track_source(payload.source)
    if source == "auto":
        source = _infer_tracking_source(target)

    config_ready = True
    if source not in {"web", "rss", "auto"}:
        matched = _matching_accounts_for_tracking(crud.list_accounts(db, user_id=current_user.id), source)
        if not matched:
            config_ready = False

    _tracking.ensure_legacy_migration(db, user_id=current_user.id, workspace=payload.workspace)
    row = _tracking.upsert_target(
        db,
        user_id=current_user.id,
        workspace=payload.workspace,
        target=target,
        source_type=(source or "web"),
        query=query,
        description=payload.description,
        tags=payload.tags,
        track_type=payload.track_type,
        interval_seconds=payload.interval_seconds,
        notify_level=payload.notify_level,
        is_temporary=bool(payload.is_temporary),
        temporary_days=payload.temporary_days,
        config_ready=config_ready,
        merge_existing=True,
    )

    note_content = (
        f"跟踪目标: {target}\n"
        f"来源: {source}\n"
        f"状态: {'active' if config_ready else 'needs_config'}\n"
        f"触发问题: {query or '未提供'}\n"
        f"时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    try:
        _memory.add_note(db, current_user.id, note_content, kind="tracking", source=f"track:{source}")
    except Exception:
        pass

    tracking_event_message_id: int | None = None
    try:
        tracking_event_message_id = _append_tracking_contact_event(
            db,
            user_id=current_user.id,
            target=target,
            source=source,
            query=query,
            status=("active" if config_ready else "needs_config"),
        )
    except Exception:
        pass

    target_id = int(row.id)
    target_workspace = str(getattr(row, "workspace", payload.workspace) or payload.workspace or "default")
    next_run = row.next_run_at.isoformat() if row.next_run_at else None
    db.commit()
    if tracking_event_message_id:
        content_tagging.enqueue_tagging_job(
            user_id=current_user.id,
            message_ids=[tracking_event_message_id],
            allow_llm=True,
        )
    if not config_ready:
        payload_settings = {"path": "/settings", "provider": source, "target_id": str(target_id)}
        if target:
            payload_settings["target"] = target[:120]
        return AelinTrackConfirmResponse(
            status="needs_config",
            message=f"已创建追踪目标“{target}”，但当前缺少 {source} 配置。",
            provider=source,
            target_id=target_id,
            next_run_at=next_run,
            actions=[
                AelinAction(
                    kind="open_settings",
                    title="去设置数据源",
                    detail=f"当前缺少 {source} 配置，打开设置页完成接入",
                    payload=payload_settings,
                )
            ],
            generated_at=datetime.now(timezone.utc),
        )

    _tracking.wake_up()
    run_result = _tracking.run_target_now(user_id=current_user.id, target_id=target_id)
    return AelinTrackConfirmResponse(
        status="tracking_enabled",
        message=f"已开启“{target}”的持续跟踪。{str(run_result.get('message') or '')}",
        provider=(source or "web"),
        target_id=target_id,
        next_run_at=next_run,
        actions=[
            AelinAction(
                kind="open_tracking",
                title="查看追踪详情",
                detail="打开追踪悬浮窗查看变化流与快照",
                payload={"target_id": str(target_id), "workspace": target_workspace},
            )
        ],
        generated_at=datetime.now(timezone.utc),
    )
