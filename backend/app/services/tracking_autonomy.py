from __future__ import annotations

import hashlib
import html
import logging
import random
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import create_session
from app.models import AgentMemoryNote, ConnectedAccount, TrackingChange, TrackingSnapshot, TrackingTarget
from app.services.encryption import encrypt_optional
from app.services.openviking_bridge import tracking_file_memory_bridge
from app.services.tracking_autonomy_utils import (
    _NOTIFY_LEVELS,
    _TRACK_STATUS,
    _json_loads_dict,
    _normalize_term_key,
    _normalize_track_type,
    _normalize_url_key,
    _normalize_workspace,
    _safe_json_dumps,
    _severity,
    _utcnow,
)
from app.services.web_search import WebSearchService
from app.settings import settings

_LOG = logging.getLogger(__name__)
_TRACKING_CONNECTOR_SOURCES = {"x", "bilibili", "douyin", "xiaohongshu", "weibo", "rss"}
_TRACKING_SOURCE_ALIAS = {
    "twitter": "x",
    "x.com": "x",
    "bili": "bilibili",
    "bilibili.com": "bilibili",
    "bsite": "bilibili",
    "xhs": "xiaohongshu",
    "rednote": "xiaohongshu",
}
_OG_URL_RE = re.compile(r'property=["\']og:url["\'][^>]*content=["\']([^"\']+)["\']', flags=re.I)
_HREF_RE = re.compile(r'href=["\'](https?://[^"\']+)["\']', flags=re.I)
_URL_RE = re.compile(r"https?://[^\s<>'\"]+", flags=re.I)


class TrackingAutonomyService:
    def __init__(self) -> None:
        self._web_search = WebSearchService(timeout_seconds=max(6.0, float(getattr(settings, "tracking_request_timeout_seconds", 15))))
        self._tick_seconds = max(0.5, float(getattr(settings, "tracking_scheduler_tick_seconds", 1.0)))
        self._batch_size = max(10, int(getattr(settings, "tracking_scheduler_batch_size", 80)))
        self._global_workers = max(1, min(24, int(getattr(settings, "tracking_global_max_workers", 16))))
        self._source_workers = max(1, min(12, int(getattr(settings, "tracking_source_max_workers", 4))))
        self._max_backoff_seconds = max(600, int(getattr(settings, "tracking_max_backoff_seconds", 21600)))
        self._error_threshold = max(3, int(getattr(settings, "tracking_error_threshold", 10)))
        self._dedupe_window_hours = max(1, int(getattr(settings, "tracking_dedupe_window_hours", 24)))
        self._min_interval = max(30, int(getattr(settings, "tracking_min_interval_seconds", 30)))
        self._default_term_interval = max(self._min_interval, int(getattr(settings, "tracking_default_term_interval_seconds", 120)))
        self._default_url_interval = max(self._min_interval, int(getattr(settings, "tracking_default_url_interval_seconds", 180)))
        self._http_timeout = max(8.0, float(getattr(settings, "tracking_request_timeout_seconds", 15)))
        self._sqlite_retry_attempts = max(1, int(getattr(settings, "tracking_sqlite_lock_retry_attempts", 4)))
        self._sqlite_retry_base_delay_seconds = max(0.05, float(getattr(settings, "tracking_sqlite_lock_retry_base_delay_seconds", 0.15)))

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(max_workers=self._global_workers, thread_name_prefix="tracking-autonomy")
        self._lock = threading.Lock()
        self._running_group_keys: set[str] = set()
        self._running_source_counts: dict[str, int] = defaultdict(int)
        self._migrated_users: set[int] = set()
        self._file_memory = tracking_file_memory_bridge

    def start(self) -> None:
        if not bool(getattr(settings, "tracking_scheduler_enabled", True)):
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="tracking-autonomy-loop")
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.5)

    def wake_up(self) -> None:
        self._wake_event.set()

    def ensure_legacy_migration(self, db: Session, *, user_id: int, workspace: str = "default") -> int:
        if user_id in self._migrated_users:
            return 0
        rows = db.scalars(
            select(AgentMemoryNote)
            .where(AgentMemoryNote.user_id == user_id, AgentMemoryNote.kind == "tracking")
            .order_by(AgentMemoryNote.updated_at.asc(), AgentMemoryNote.id.asc())
            .limit(500)
        ).all()
        created = 0
        for note in rows:
            parsed = self._parse_legacy_tracking_note(note.content or "")
            target = (parsed.get("target") or "").strip()
            if not target:
                continue
            self.upsert_target(
                db,
                user_id=user_id,
                workspace=workspace,
                target=target,
                source_type=parsed.get("source") or "web",
                query=parsed.get("query") or "",
                description="",
                tags=[],
                track_type=None,
                interval_seconds=None,
                notify_level="all",
                is_temporary=False,
                temporary_days=7,
                config_ready=True,
                merge_existing=True,
            )
            created += 1
        self._migrated_users.add(user_id)
        return created

    def upsert_target(self, db: Session, *, user_id: int, workspace: str, target: str, source_type: str, query: str, description: str, tags: list[str], track_type: str | None, interval_seconds: int | None, notify_level: str, is_temporary: bool, temporary_days: int, config_ready: bool, merge_existing: bool) -> TrackingTarget:
        workspace_norm = _normalize_workspace(workspace)
        target_text = (target or "").strip()[:500]
        if not target_text:
            raise ValueError("target is empty")
        track_type_norm = _normalize_track_type(track_type, target_text)
        source_key = _normalize_url_key(target_text) if track_type_norm == "url" else _normalize_term_key(target_text)
        if not source_key:
            raise ValueError("target key is empty")

        interval = int(interval_seconds or 0)
        if interval <= 0:
            interval = self._default_url_interval if track_type_norm == "url" else self._default_term_interval
        interval = max(self._min_interval, min(86400, interval))

        notify = (notify_level or "all").strip().lower()
        if notify not in _NOTIFY_LEVELS:
            notify = "all"

        row: TrackingTarget | None = None
        if merge_existing:
            row = db.scalar(
                select(TrackingTarget)
                .where(
                    TrackingTarget.user_id == user_id,
                    TrackingTarget.workspace == workspace_norm,
                    TrackingTarget.track_type == track_type_norm,
                    TrackingTarget.source_key == source_key,
                    TrackingTarget.deleted_at.is_(None),
                    TrackingTarget.status != "deleted",
                )
                .order_by(TrackingTarget.updated_at.desc(), TrackingTarget.id.desc())
                .limit(1)
            )

        now = _utcnow()
        expires_at = now + timedelta(days=max(1, min(30, int(temporary_days or 7)))) if is_temporary else None
        tags_norm = sorted({str(tag).strip()[:32] for tag in tags if str(tag).strip()})

        if row is None:
            row = TrackingTarget(
                user_id=user_id,
                workspace=workspace_norm,
                track_type=track_type_norm,
                source_type=(source_type or "web").strip().lower() or "web",
                source_key=source_key,
                display_name=target_text[:255],
                description=(description or "").strip()[:1200] or None,
                tags_json=_safe_json_dumps(tags_norm),
                interval_seconds=interval,
                status="active" if config_ready else "paused",
                config_ready=bool(config_ready),
                notify_level=notify,
                is_temporary=bool(is_temporary),
                expires_at=expires_at,
                next_run_at=now + timedelta(seconds=random.randint(1, 4)),
                config_json=_safe_json_dumps({"query": (query or "").strip()[:500], "target": target_text}),
            )
            db.add(row)
            db.flush()
            self._file_memory.sync_target_profile(row)
            return row

        row.source_type = (source_type or row.source_type or "web").strip().lower() or "web"
        row.display_name = target_text[:255]
        if description is not None:
            row.description = (description or "").strip()[:1200] or row.description
        if tags_norm:
            row.tags_json = _safe_json_dumps(tags_norm)
        row.interval_seconds = interval
        row.notify_level = notify
        row.config_ready = bool(config_ready)
        row.status = "active" if config_ready else "paused"
        row.is_temporary = bool(is_temporary)
        row.expires_at = expires_at
        row.deleted_at = None
        row.next_run_at = now + timedelta(seconds=random.randint(1, 4))
        cfg = _json_loads_dict(row.config_json)
        cfg.update({"query": (query or "").strip()[:500], "target": target_text})
        row.config_json = _safe_json_dumps(cfg)
        db.add(row)
        db.flush()
        self._file_memory.sync_target_profile(row)
        return row

    def list_targets(self, db: Session, *, user_id: int, workspace: str | None, limit: int, status: str | None = None, include_deleted: bool = False) -> list[TrackingTarget]:
        q = select(TrackingTarget).where(TrackingTarget.user_id == user_id)
        if workspace:
            q = q.where(TrackingTarget.workspace == _normalize_workspace(workspace))
        if status and status in _TRACK_STATUS:
            q = q.where(TrackingTarget.status == status)
        elif not include_deleted:
            q = q.where(TrackingTarget.status != "deleted", TrackingTarget.deleted_at.is_(None))
        return list(db.scalars(q.order_by(TrackingTarget.updated_at.desc(), TrackingTarget.id.desc()).limit(max(1, min(500, limit)))))

    def update_target(self, db: Session, *, user_id: int, target_id: int, status: str | None, interval_seconds: int | None, notify_level: str | None, mute_until: datetime | None, description: str | None, tags: list[str] | None) -> TrackingTarget | None:
        row = db.get(TrackingTarget, target_id)
        if row is None or row.user_id != user_id:
            return None
        if status and status in _TRACK_STATUS:
            row.status = status
            if status == "deleted":
                row.deleted_at = _utcnow()
            elif status in {"active", "paused", "error"}:
                row.deleted_at = None
        if interval_seconds is not None:
            row.interval_seconds = max(self._min_interval, min(86400, int(interval_seconds)))
        if notify_level:
            level = notify_level.strip().lower()
            if level in _NOTIFY_LEVELS:
                row.notify_level = level
        row.mute_until = mute_until
        if description is not None:
            row.description = description.strip()[:1200] or None
        if tags is not None:
            row.tags_json = _safe_json_dumps(sorted({str(tag).strip()[:32] for tag in tags if str(tag).strip()}))
        if row.status == "active" and row.next_run_at is None:
            row.next_run_at = _utcnow() + timedelta(seconds=random.randint(1, 4))
        db.add(row)
        db.flush()
        self._file_memory.sync_target_profile(row)
        self.wake_up()
        return row

    def ack_change(self, db: Session, *, user_id: int, change_id: int) -> TrackingChange | None:
        row = db.get(TrackingChange, change_id)
        if row is None:
            return None
        target = db.get(TrackingTarget, row.target_id)
        if target is None or target.user_id != user_id:
            return None
        row.acked = True
        row.acked_at = _utcnow()
        db.add(row)
        db.flush()
        return row
    def list_changes(self, db: Session, *, user_id: int, target_id: int, limit: int, severity: str | None = None, change_type: str | None = None, acked: bool | None = None) -> list[TrackingChange]:
        target = db.get(TrackingTarget, target_id)
        if target is None or target.user_id != user_id:
            return []
        q = select(TrackingChange).where(TrackingChange.target_id == target_id)
        if severity:
            q = q.where(TrackingChange.severity == severity)
        if change_type:
            q = q.where(TrackingChange.change_type == change_type)
        if acked is not None:
            q = q.where(TrackingChange.acked.is_(bool(acked)))
        return list(db.scalars(q.order_by(TrackingChange.created_at.desc(), TrackingChange.id.desc()).limit(max(1, min(500, limit)))))

    def list_snapshots(self, db: Session, *, user_id: int, target_id: int, limit: int) -> list[TrackingSnapshot]:
        target = db.get(TrackingTarget, target_id)
        if target is None or target.user_id != user_id:
            return []
        q = (
            select(TrackingSnapshot)
            .where(TrackingSnapshot.target_id == target_id)
            .order_by(TrackingSnapshot.version_no.desc(), TrackingSnapshot.id.desc())
            .limit(max(1, min(300, limit)))
        )
        return list(db.scalars(q))

    def run_target_now(self, *, user_id: int, target_id: int) -> dict[str, Any]:
        max_attempts = max(1, int(self._sqlite_retry_attempts))
        for attempt in range(1, max_attempts + 1):
            db = create_session()
            group_key = ""
            source = "web"
            group_marked = False
            try:
                target = db.get(TrackingTarget, target_id)
                if target is None or target.user_id != user_id:
                    return {"ok": False, "message": "target not found"}
                if target.status == "deleted" or target.deleted_at is not None:
                    return {"ok": False, "message": "target deleted"}
                if target.status != "active":
                    return {"ok": False, "message": f"target status is {target.status}"}

                group_key = self._group_key(target)
                source = target.source_type or "web"
                if not self._mark_group_running(group_key, source):
                    return {"ok": False, "message": "target is busy, retry in a few seconds"}
                group_marked = True

                stats = self._run_target_ids(db, [int(target_id)])
                db.commit()

                fetched_count = int(stats.get("fetched_count", 0))
                snapshots_created = int(stats.get("snapshots_created", 0))
                changes_created = int(stats.get("changes_created", 0))
                if snapshots_created == 0 and fetched_count == 0:
                    message = "run completed: source_no_result (no snapshots/changes yet)"
                else:
                    message = f"run completed: fetched={fetched_count}, snapshots={snapshots_created}, changes={changes_created}"
                return {"ok": True, "message": message}
            except OperationalError as exc:
                db.rollback()
                if self._is_sqlite_locked_error(exc) and attempt < max_attempts:
                    _LOG.warning(
                        "tracking run_target_now locked: target_id=%s attempt=%s/%s",
                        target_id,
                        attempt,
                        max_attempts,
                    )
                    self._sleep_sqlite_retry_backoff(attempt)
                    continue
                if self._is_sqlite_locked_error(exc):
                    return {"ok": False, "message": "run failed: database is busy, retry in a few seconds"}
                return {"ok": False, "message": f"run failed: {str(exc)[:220]}"}
            except Exception as exc:
                db.rollback()
                return {"ok": False, "message": f"run failed: {str(exc)[:220]}"}
            finally:
                if group_marked and group_key:
                    self._unmark_group_running(group_key, source)
                db.close()

    def build_notification_items(self, db: Session, *, user_id: int, limit: int = 20) -> tuple[list[dict[str, Any]], list[int]]:
        q = (
            select(TrackingChange, TrackingTarget)
            .join(TrackingTarget, TrackingTarget.id == TrackingChange.target_id)
            .where(
                TrackingTarget.user_id == user_id,
                TrackingTarget.status != "deleted",
                TrackingChange.acked.is_(False),
            )
            .order_by(TrackingChange.created_at.desc(), TrackingChange.id.desc())
            .limit(max(20, min(400, limit * 8)))
        )
        rows = db.execute(q).all()
        items: list[dict[str, Any]] = []
        to_mark: list[int] = []
        seen: set[str] = set()
        for change, target in rows:
            if not self._notify_pass(target.notify_level, change.severity):
                continue
            dedupe_key = change.dedupe_key or f"chg:{change.id}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            level = "info"
            if change.severity == "critical":
                level = "error"
            elif change.severity == "high":
                level = "warning"
            elif change.change_type in {"new_item", "recovered"}:
                level = "success"
            items.append(
                {
                    "id": f"tracking-change-{change.id}",
                    "level": level,
                    "title": f"[{target.display_name}] {change.title or change.change_type}",
                    "detail": change.summary or "",
                    "source": "tracking",
                    "ts": change.created_at.isoformat() if change.created_at else "",
                    "action_kind": "open_tracking",
                    "action_payload": {
                        "target_id": str(target.id),
                        "change_id": str(change.id),
                        "workspace": target.workspace,
                    },
                }
            )
            if not change.notified:
                to_mark.append(int(change.id))
            if len(items) >= limit:
                break
        return items, to_mark

    def mark_notified(self, db: Session, *, change_ids: list[int]) -> None:
        ids = [int(cid) for cid in change_ids if int(cid) > 0]
        if not ids:
            return
        now = _utcnow()
        rows = list(db.scalars(select(TrackingChange).where(TrackingChange.id.in_(ids))))
        for row in rows:
            row.notified = True
            row.notified_at = now
            db.add(row)
        db.flush()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._dispatch_due_once()
            except Exception as exc:  # pragma: no cover
                _LOG.exception("tracking loop error: %s", exc)
            self._wake_event.wait(self._tick_seconds)
            self._wake_event.clear()

    def _dispatch_due_once(self, *, force_target_id: int | None = None) -> int:
        db = create_session()
        try:
            now = _utcnow()
            q = select(TrackingTarget).where(TrackingTarget.status == "active", TrackingTarget.deleted_at.is_(None))
            if force_target_id:
                q = q.where(TrackingTarget.id == int(force_target_id))
            else:
                q = q.where(TrackingTarget.config_ready.is_(True), TrackingTarget.next_run_at.is_not(None), TrackingTarget.next_run_at <= now)
            rows = list(db.scalars(q.order_by(TrackingTarget.next_run_at.asc(), TrackingTarget.id.asc()).limit(self._batch_size)))
            if not rows:
                return 0

            groups: dict[str, list[int]] = defaultdict(list)
            source_by_group: dict[str, str] = {}
            for row in rows:
                expires_at = self._as_utc_datetime(row.expires_at)
                if row.is_temporary and expires_at and expires_at <= now:
                    row.status = "paused"
                    db.add(row)
                    continue
                gkey = self._group_key(row)
                groups[gkey].append(int(row.id))
                source_by_group[gkey] = row.source_type or "web"
            db.flush()

            scheduled = 0
            for gkey, ids in groups.items():
                source = source_by_group.get(gkey, "web")
                if not self._mark_group_running(gkey, source):
                    continue
                self._executor.submit(self._run_group_worker, gkey, source, ids)
                scheduled += 1
            return scheduled
        finally:
            db.close()

    def _mark_group_running(self, group_key: str, source: str) -> bool:
        with self._lock:
            if group_key in self._running_group_keys:
                return False
            if len(self._running_group_keys) >= self._global_workers:
                return False
            if self._running_source_counts[source] >= self._source_workers:
                return False
            self._running_group_keys.add(group_key)
            self._running_source_counts[source] += 1
            return True

    def _unmark_group_running(self, group_key: str, source: str) -> None:
        with self._lock:
            self._running_group_keys.discard(group_key)
            self._running_source_counts[source] = max(0, self._running_source_counts[source] - 1)

    def _run_group_worker(self, group_key: str, source: str, target_ids: list[int]) -> None:
        try:
            for attempt in range(1, self._sqlite_retry_attempts + 1):
                db = create_session()
                try:
                    self._run_target_ids(db, target_ids)
                    db.commit()
                    return
                except OperationalError as exc:
                    db.rollback()
                    if self._is_sqlite_locked_error(exc) and attempt < self._sqlite_retry_attempts:
                        _LOG.warning(
                            "tracking worker locked: group=%s attempt=%s/%s",
                            group_key,
                            attempt,
                            self._sqlite_retry_attempts,
                        )
                        self._sleep_sqlite_retry_backoff(attempt)
                        continue
                    _LOG.exception("tracking worker failed: %s", exc)
                    return
                except Exception as exc:  # pragma: no cover
                    db.rollback()
                    _LOG.exception("tracking worker failed: %s", exc)
                    return
                finally:
                    db.close()
        finally:
            self._unmark_group_running(group_key, source)

    def _notify_pass(self, notify_level: str, severity: str) -> bool:
        level = (notify_level or "all").strip().lower()
        sev = (severity or "low").strip().lower()
        rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        need = 1
        if level == "important":
            need = 2
        elif level == "critical":
            need = 4
        return rank.get(sev, 1) >= need
    def _run_target_ids(self, db: Session, target_ids: list[int]) -> dict[str, int]:
        stats = {"targets": 0, "fetched_count": 0, "snapshots_created": 0, "changes_created": 0, "errors": 0}
        if not target_ids:
            return stats
        targets = list(
            db.scalars(
                select(TrackingTarget)
                .where(TrackingTarget.id.in_(target_ids), TrackingTarget.status == "active", TrackingTarget.deleted_at.is_(None))
                .order_by(TrackingTarget.id.asc())
            )
        )
        if not targets:
            return stats

        stats["targets"] = len(targets)
        primary = targets[0]
        now = _utcnow()
        try:
            raw_payload, normalized_payload = self._fetch_payload(db, primary)
        except Exception as exc:
            err = str(exc or "fetch failed")[:500]
            for target in targets:
                self._apply_fetch_error(db, target, err, now=now)
                stats["errors"] += 1
            return stats

        payload_hash = hashlib.sha256(_safe_json_dumps(normalized_payload).encode("utf-8")).hexdigest()
        fetched_count = len((normalized_payload.get("items") or [])) if isinstance(normalized_payload, dict) else 0
        stats["fetched_count"] = max(0, int(fetched_count))
        for target in targets:
            self._file_memory.sync_target_profile(target)
            target.last_run_at = now
            target.last_checked_at = now
            target.next_run_at = self._next_run_time(interval_seconds=target.interval_seconds, error_count=0)
            expires_at = self._as_utc_datetime(target.expires_at)
            if target.is_temporary and expires_at and expires_at <= now:
                target.status = "paused"
                db.add(target)
                continue

            prev_snapshot = db.scalar(
                select(TrackingSnapshot)
                .where(TrackingSnapshot.target_id == target.id)
                .order_by(TrackingSnapshot.version_no.desc(), TrackingSnapshot.id.desc())
                .limit(1)
            )
            prev_hash = (target.last_hash or "").strip()
            prev_error_count = int(target.error_count or 0)
            target.error_count = 0
            target.last_hash = payload_hash
            if target.status == "error":
                target.status = "active"

            if prev_hash == payload_hash and prev_snapshot is not None:
                if prev_error_count > 0:
                    recovered = self._create_change(
                        db,
                        target=target,
                        from_snapshot=prev_snapshot,
                        to_snapshot=prev_snapshot,
                        change_type="recovered",
                        title="抓取恢复",
                        summary="目标恢复正常抓取。",
                        diff_payload={"error_count_before": prev_error_count},
                        fingerprint="recovered",
                        now=now,
                    )
                    if recovered is not None:
                        stats["changes_created"] += 1
                db.add(target)
                continue

            next_version = int(prev_snapshot.version_no + 1) if prev_snapshot is not None else 1
            raw_json = _safe_json_dumps(raw_payload)
            normalized_json = _safe_json_dumps(normalized_payload)
            snapshot = TrackingSnapshot(
                target_id=int(target.id),
                version_no=next_version,
                raw_payload_json=encrypt_optional(raw_json) or raw_json,
                normalized_payload_json=normalized_json,
                content_hash=payload_hash,
                fetched_at=now,
                fetch_status="ok" if fetched_count > 0 else "partial",
                fetch_error=None if fetched_count > 0 else "source_no_result",
            )
            db.add(snapshot)
            db.flush()
            self._file_memory.append_snapshot(target=target, snapshot=snapshot, normalized_payload=normalized_payload)
            stats["snapshots_created"] += 1

            prev_normalized = _json_loads_dict(prev_snapshot.normalized_payload_json) if prev_snapshot else {}
            changes = self._diff_changes(prev_payload=prev_normalized, next_payload=normalized_payload)
            if not changes and prev_snapshot is None:
                changes = [{
                    "change_type": "new_item",
                    "title": "追踪已启动",
                    "summary": f"初次抓取完成，当前捕获 {len((normalized_payload.get('items') or []))} 条。",
                    "diff": {"baseline": True, "count": len((normalized_payload.get('items') or []))},
                    "fingerprint": "baseline",
                }]
            for item in changes:
                created = self._create_change(
                    db,
                    target=target,
                    from_snapshot=prev_snapshot,
                    to_snapshot=snapshot,
                    change_type=str(item.get("change_type") or "updated_item"),
                    title=str(item.get("title") or "变化"),
                    summary=str(item.get("summary") or "")[:900],
                    diff_payload=item.get("diff") if isinstance(item.get("diff"), dict) else {},
                    fingerprint=str(item.get("fingerprint") or "generic"),
                    now=now,
                )
                if created is not None:
                    stats["changes_created"] += 1
            if changes:
                target.last_change_at = now
            db.add(target)

        return stats

    def _apply_fetch_error(self, db: Session, target: TrackingTarget, error: str, *, now: datetime) -> None:
        prev_status = target.status
        target.last_run_at = now
        target.last_checked_at = now
        target.error_count = int(target.error_count or 0) + 1
        if target.error_count >= self._error_threshold:
            target.status = "error"
        target.next_run_at = self._next_run_time(interval_seconds=target.interval_seconds, error_count=target.error_count)
        db.add(target)

        snapshot = TrackingSnapshot(
            target_id=int(target.id),
            version_no=0,
            raw_payload_json=encrypt_optional(_safe_json_dumps({"error": error})) or _safe_json_dumps({"error": error}),
            normalized_payload_json="{}",
            content_hash="",
            fetched_at=now,
            fetch_status="failed",
            fetch_error=error[:500],
        )
        db.add(snapshot)
        db.flush()
        self._file_memory.append_snapshot(target=target, snapshot=snapshot, normalized_payload={})
        self._file_memory.sync_target_profile(target)

        self._create_change(
            db,
            target=target,
            from_snapshot=None,
            to_snapshot=snapshot,
            change_type="fetch_error",
            title="抓取失败",
            summary=error[:300],
            diff_payload={"error_count": target.error_count},
            fingerprint=error[:120],
            now=now,
        )
        if prev_status != target.status:
            self._create_change(
                db,
                target=target,
                from_snapshot=None,
                to_snapshot=snapshot,
                change_type="status_change",
                title="状态变化",
                summary=f"状态从 {prev_status} 变为 {target.status}",
                diff_payload={"from": prev_status, "to": target.status},
                fingerprint=f"{prev_status}->{target.status}",
                now=now,
            )

    def _fetch_payload(self, db: Session, target: TrackingTarget) -> tuple[dict[str, Any], dict[str, Any]]:
        config = _json_loads_dict(target.config_json)
        query = (str(config.get("query") or "").strip() or target.display_name or target.source_key).strip()
        if target.track_type == "url":
            url = _normalize_url_key(target.source_key or target.display_name)
            if not url:
                raise ValueError("invalid target url")
            title, excerpt = self._web_search.fetch_page_excerpt(url, max_chars=2200)
            links = self._extract_url_links(url)
            items = [{"key": url, "url": url, "title": title or urlparse(url).netloc, "snippet": excerpt[:300]}, *links]
            return (
                {"kind": "url", "url": url, "title": title, "excerpt": excerpt, "links": links, "fetched_at": _utcnow().isoformat()},
                {"kind": "url", "source_key": url, "items": items[:40], "meta": {"count": len(items)}},
            )

        source_type = self._normalize_source_type(target.source_type)
        if source_type in _TRACKING_CONNECTOR_SOURCES:
            connector_payload = self._fetch_payload_via_connector(
                db,
                target=target,
                query=query,
                source_type=source_type,
            )
            if connector_payload is not None:
                return connector_payload

        rows = self._web_search.search_and_fetch(query, max_results=15, fetch_top_k=5)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            key = (row.url or "").strip().lower() or hashlib.sha1((row.title or "").encode("utf-8", errors="ignore")).hexdigest()
            if not key or key in seen:
                continue
            seen.add(key)
            items.append({"key": key[:240], "url": row.url, "title": row.title, "snippet": (row.fetched_excerpt or row.snippet or "")[:300], "provider": row.provider, "fetch_mode": row.fetch_mode})
        return (
            {
                "kind": "term",
                "query": query,
                "rows": [{"title": row.title, "url": row.url, "snippet": row.snippet, "fetched_excerpt": row.fetched_excerpt, "provider": row.provider, "fetch_mode": row.fetch_mode, "rank": row.rank} for row in rows],
                "fetched_at": _utcnow().isoformat(),
                "source": source_type,
                "fetch_path": "web_search",
            },
            {"kind": "term", "source_key": target.source_key, "items": items[:40], "meta": {"count": len(items), "query": query, "source": source_type, "fetch_path": "web_search"}},
        )

    def _normalize_source_type(self, source_type: str | None) -> str:
        clean = (source_type or "").strip().lower()
        if not clean:
            return "web"
        return _TRACKING_SOURCE_ALIAS.get(clean, clean)

    def _fetch_payload_via_connector(
        self,
        db: Session,
        *,
        target: TrackingTarget,
        query: str,
        source_type: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        accounts = self._matching_connector_accounts(db, target=target, source_type=source_type, query=query)
        if not accounts:
            _LOG.info(
                "tracking connector skipped: no account user_id=%s source=%s target=%s",
                target.user_id,
                source_type,
                target.display_name or target.source_key,
            )
            return None

        try:
            from app.sync import _connector_for  # lazy import to avoid heavy startup dependency
        except Exception as exc:
            _LOG.warning("tracking connector unavailable source=%s error=%s", source_type, str(exc)[:240])
            return None

        attempt_errors: list[str] = []
        for account in accounts:
            account_label = f"{source_type}:{getattr(account, 'id', 0)}:{getattr(account, 'identifier', '')}"
            try:
                connector = _connector_for(db, account)
            except Exception as exc:
                attempt_errors.append(f"{account_label}:init:{str(exc)[:140]}")
                continue

            try:
                messages = connector.fetch_new_messages(since=None)
            except Exception as exc:
                attempt_errors.append(f"{account_label}:fetch:{str(exc)[:140]}")
                continue

            payload = self._build_connector_payload(
                target=target,
                query=query,
                source_type=source_type,
                account=account,
                messages=messages,
            )
            if payload is None:
                attempt_errors.append(f"{account_label}:empty")
                continue
            return payload

        if attempt_errors:
            _LOG.info(
                "tracking connector fallback to web_search user_id=%s source=%s details=%s",
                target.user_id,
                source_type,
                "; ".join(attempt_errors[:6]),
            )
        return None

    def _matching_connector_accounts(
        self,
        db: Session,
        *,
        target: TrackingTarget,
        source_type: str,
        query: str,
    ) -> list[ConnectedAccount]:
        rows = list(
            db.scalars(
                select(ConnectedAccount)
                .where(
                    ConnectedAccount.user_id == int(target.user_id),
                    func.lower(ConnectedAccount.provider) == source_type,
                )
                .order_by(ConnectedAccount.id.asc())
            )
        )
        if not rows:
            return []

        config = _json_loads_dict(target.config_json)
        preferred_account_id = 0
        try:
            preferred_account_id = int(config.get("account_id") or 0)
        except Exception:
            preferred_account_id = 0
        source_hint = " ".join(
            [
                str(target.display_name or ""),
                str(target.source_key or ""),
                str(query or ""),
                str(config.get("query") or ""),
                str(config.get("target") or ""),
            ]
        ).strip().lower()

        def _score(account: ConnectedAccount) -> tuple[int, int]:
            score = 0
            if preferred_account_id > 0 and int(account.id) == preferred_account_id:
                score += 1000
            identifier = str(getattr(account, "identifier", "") or "").strip().lower()
            if identifier:
                if identifier in source_hint:
                    score += 120
                token = identifier.split(":", 1)[-1].split("/")[-1].lstrip("@").strip()
                if token and token in source_hint:
                    score += 160
            feed_cfg = getattr(account, "feed_config", None)
            if feed_cfg is not None:
                display_name = str(getattr(feed_cfg, "display_name", "") or "").strip().lower()
                homepage_url = str(getattr(feed_cfg, "homepage_url", "") or "").strip().lower()
                feed_url = str(getattr(feed_cfg, "feed_url", "") or "").strip().lower()
                for hint in (display_name, homepage_url, feed_url):
                    if hint and hint in source_hint:
                        score += 90
            return score, int(account.id)

        return sorted(rows, key=_score, reverse=True)

    def _build_connector_payload(
        self,
        *,
        target: TrackingTarget,
        query: str,
        source_type: str,
        account: ConnectedAccount,
        messages: list[Any],
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if not messages:
            return None

        def _message_sort_ts(row: Any) -> float:
            received = getattr(row, "received_at", None)
            if isinstance(received, datetime):
                if received.tzinfo is None:
                    received = received.replace(tzinfo=_utcnow().tzinfo)
                return float(received.timestamp())
            return 0.0

        ordered = sorted(
            [item for item in messages if item is not None],
            key=_message_sort_ts,
            reverse=True,
        )
        items: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for msg in ordered[:120]:
            normalized = self._normalize_connector_message(msg=msg, source_type=source_type)
            if normalized is None:
                continue
            key = str(normalized.get("key") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            item = {
                "key": key[:240],
                "url": normalized.get("url") or "",
                "title": normalized.get("title") or "",
                "snippet": str(normalized.get("snippet") or "")[:300],
                "provider": source_type,
                "fetch_mode": "connector",
                "published_at": normalized.get("published_at") or "",
                "sender": normalized.get("sender") or "",
            }
            items.append(item)
            rows.append(
                {
                    "external_id": normalized.get("external_id") or "",
                    "title": item["title"],
                    "url": item["url"],
                    "snippet": item["snippet"],
                    "published_at": item["published_at"],
                    "sender": item["sender"],
                    "source": source_type,
                    "fetch_mode": "connector",
                }
            )
            if len(items) >= 40:
                break

        if not items:
            return None

        now_iso = _utcnow().isoformat()
        account_id = int(getattr(account, "id", 0) or 0)
        account_identifier = str(getattr(account, "identifier", "") or "").strip()
        raw_payload = {
            "kind": "term",
            "query": query,
            "source": source_type,
            "fetch_path": "connector",
            "account_id": account_id,
            "account_identifier": account_identifier,
            "rows": rows,
            "fetched_at": now_iso,
        }
        normalized_payload = {
            "kind": "term",
            "source_key": target.source_key,
            "items": items,
            "meta": {
                "count": len(items),
                "query": query,
                "source": source_type,
                "fetch_path": "connector",
                "account_id": account_id,
                "account_identifier": account_identifier,
            },
        }
        return raw_payload, normalized_payload

    def _normalize_connector_message(self, *, msg: Any, source_type: str) -> dict[str, str] | None:
        subject = str(getattr(msg, "subject", "") or "").strip()
        body = str(getattr(msg, "body", "") or "")
        sender = str(getattr(msg, "sender", "") or "").strip()
        external_id = str(getattr(msg, "external_id", "") or "").strip()
        received_at = getattr(msg, "received_at", None)

        title = subject or sender or f"{source_type} update"
        snippet = self._strip_html(body)
        if not snippet:
            snippet = title
        url = self._extract_message_url(body)
        if not url:
            url = self._extract_message_url(subject)
        published_at = ""
        if isinstance(received_at, datetime):
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=_utcnow().tzinfo)
            published_at = received_at.isoformat()

        if external_id:
            key = f"{source_type}:{external_id}".strip().lower()
        elif url:
            key = _normalize_url_key(url)
        else:
            key_seed = f"{source_type}:{sender}:{title}:{published_at}".lower()
            key = hashlib.sha1(key_seed.encode("utf-8", errors="ignore")).hexdigest()
        key = (key or "").strip()[:240]
        if not key:
            return None
        return {
            "key": key,
            "url": url,
            "title": title[:220],
            "snippet": snippet[:300],
            "sender": sender[:120],
            "external_id": external_id[:120],
            "published_at": published_at,
        }

    def _strip_html(self, text: str) -> str:
        clean = html.unescape(str(text or ""))
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:1200]

    def _extract_message_url(self, text: str) -> str:
        content = str(text or "")
        match = _OG_URL_RE.search(content)
        if match:
            normalized = _normalize_url_key(match.group(1))
            if normalized:
                return normalized
        match = _HREF_RE.search(content)
        if match:
            normalized = _normalize_url_key(match.group(1))
            if normalized:
                return normalized
        match = _URL_RE.search(content)
        if match:
            normalized = _normalize_url_key(match.group(0))
            if normalized:
                return normalized
        return ""

    def _extract_url_links(self, url: str) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        try:
            with httpx.Client(timeout=self._http_timeout, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
            if resp.status_code >= 400:
                return []
            html_text = resp.text or ""
        except Exception:
            return []

        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for match in re.finditer(r"<a[^>]+href=['\"](?P<href>[^'\"]+)['\"][^>]*>(?P<title>[\s\S]*?)</a>", html_text, flags=re.I):
            href = (match.group("href") or "").strip()
            if not href or href.startswith(("javascript:", "mailto:", "#")):
                continue
            full_url = urljoin(url, href)
            if not full_url.startswith(("http://", "https://")):
                continue
            norm = _normalize_url_key(full_url)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            title = re.sub(r"<[^>]+>", " ", match.group("title") or "")
            title = re.sub(r"\s+", " ", title).strip()
            rows.append({"key": norm[:240], "url": norm, "title": (title or urlparse(norm).netloc)[:220], "snippet": ""})
            if len(rows) >= 40:
                break
        return rows

    def _diff_changes(self, *, prev_payload: dict[str, Any], next_payload: dict[str, Any]) -> list[dict[str, Any]]:
        prev_items = {str(item.get("key") or ""): item for item in (prev_payload.get("items") or []) if isinstance(item, dict) and str(item.get("key") or "")}
        next_items = {str(item.get("key") or ""): item for item in (next_payload.get("items") or []) if isinstance(item, dict) and str(item.get("key") or "")}

        added = [k for k in next_items.keys() if k not in prev_items]
        removed = [k for k in prev_items.keys() if k not in next_items]
        changed: list[str] = []
        for key, cur in next_items.items():
            prev = prev_items.get(key)
            if prev is None:
                continue
            prev_sig = hashlib.sha1(_safe_json_dumps({"title": prev.get("title"), "snippet": prev.get("snippet")}).encode("utf-8")).hexdigest()
            cur_sig = hashlib.sha1(_safe_json_dumps({"title": cur.get("title"), "snippet": cur.get("snippet")}).encode("utf-8")).hexdigest()
            if prev_sig != cur_sig:
                changed.append(key)

        out: list[dict[str, Any]] = []
        for key in added[:6]:
            item = next_items[key]
            out.append({"change_type": "new_item", "title": "发现新内容", "summary": str(item.get("title") or item.get("url") or "新增条目")[:280], "diff": {"added": item}, "fingerprint": f"new:{key}"})
        for key in changed[:4]:
            item = next_items[key]
            out.append({"change_type": "updated_item", "title": "内容更新", "summary": str(item.get("title") or item.get("url") or "更新条目")[:280], "diff": {"updated": item}, "fingerprint": f"upd:{key}"})
        if removed:
            out.append({"change_type": "removed_item", "title": "内容减少", "summary": f"检测到 {len(removed)} 条历史项不再出现。", "diff": {"removed_count": len(removed), "removed_keys": removed[:12]}, "fingerprint": f"removed:{len(removed)}"})
        prev_count = len(prev_items)
        next_count = len(next_items)
        if prev_count > 0 and next_count >= prev_count + 5 and (next_count - prev_count) / float(prev_count) >= 0.5:
            out.append({"change_type": "metric_spike", "title": "更新量突增", "summary": f"条目数量从 {prev_count} 增至 {next_count}。", "diff": {"from": prev_count, "to": next_count}, "fingerprint": f"spike:{prev_count}->{next_count}"})
        return out

    def _create_change(self, db: Session, *, target: TrackingTarget, from_snapshot: TrackingSnapshot | None, to_snapshot: TrackingSnapshot | None, change_type: str, title: str, summary: str, diff_payload: dict[str, Any], fingerprint: str, now: datetime) -> TrackingChange | None:
        dedupe_seed = f"{target.user_id}:{target.workspace}:{target.track_type}:{target.source_key}:{change_type}:{fingerprint}:{now.strftime('%Y%m%d')}"
        dedupe_key = hashlib.sha1(dedupe_seed.encode("utf-8")).hexdigest()
        since = now - timedelta(hours=self._dedupe_window_hours)
        exists = db.scalar(
            select(func.count(TrackingChange.id))
            .join(TrackingTarget, TrackingTarget.id == TrackingChange.target_id)
            .where(TrackingTarget.user_id == target.user_id, TrackingChange.dedupe_key == dedupe_key, TrackingChange.created_at >= since)
        )
        if int(exists or 0) > 0:
            return None
        row = TrackingChange(
            target_id=int(target.id),
            from_snapshot_id=int(from_snapshot.id) if from_snapshot else None,
            to_snapshot_id=int(to_snapshot.id) if to_snapshot else None,
            change_type=change_type,
            severity=_severity(change_type),
            title=title[:255],
            summary=summary[:1200],
            diff_json=_safe_json_dumps(diff_payload),
            dedupe_key=dedupe_key,
            notified=False,
            acked=False,
            created_at=now,
        )
        db.add(row)
        db.flush()
        self._file_memory.append_change(target=target, change=row, diff_payload=diff_payload if isinstance(diff_payload, dict) else {})
        return row

    def _next_run_time(self, *, interval_seconds: int, error_count: int) -> datetime:
        now = _utcnow()
        base = max(self._min_interval, int(interval_seconds or self._default_term_interval))
        if error_count <= 0:
            return now + timedelta(seconds=base + random.randint(1, 9))
        backoff = min(self._max_backoff_seconds, max(base, (2 ** max(0, error_count - 1)) * base))
        return now + timedelta(seconds=backoff + random.randint(1, 12))

    def _as_utc_datetime(self, value: datetime | None) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _group_key(self, row: TrackingTarget) -> str:
        return f"{row.user_id}:{row.workspace}:{row.track_type}:{row.source_type}:{row.source_key}".lower()

    def _is_sqlite_locked_error(self, exc: Exception) -> bool:
        text = str(getattr(exc, "orig", exc) or exc).lower()
        return "database is locked" in text or "database table is locked" in text

    def _sleep_sqlite_retry_backoff(self, attempt: int) -> None:
        base = self._sqlite_retry_base_delay_seconds
        delay = min(1.6, base * (2 ** max(0, attempt - 1)) + random.uniform(0.0, base))
        time.sleep(delay)

    def _parse_legacy_tracking_note(self, text: str) -> dict[str, str]:
        content = (text or "").strip()
        if not content:
            return {}

        def _extract(label: str) -> str:
            match = re.search(rf"{re.escape(label)}\s*[:：]\s*(.+)", content, flags=re.I)
            if not match:
                return ""
            return (match.group(1) or "").strip().splitlines()[0].strip()

        return {"target": _extract("跟踪目标"), "source": _extract("来源") or "web", "query": _extract("触发问题")}


tracking_autonomy_service = TrackingAutonomyService()






