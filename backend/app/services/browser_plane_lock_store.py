from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select

from app.db import create_session
from app.models import BrowserPlaneTabLock


def _normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _lock_row_to_payload(row: BrowserPlaneTabLock) -> dict[str, Any]:
    expires_at = _as_utc_datetime(row.expires_at)
    return {
        "tab_id": str(row.tab_id or ""),
        "workspace": str(row.workspace or "default"),
        "owner": str(row.owner or ""),
        "reason": str(row.reason or ""),
        "expires_at": expires_at.timestamp() if expires_at is not None else 0.0,
        "created_at": _as_utc_datetime(row.created_at).timestamp() if row.created_at else 0.0,
        "updated_at": _as_utc_datetime(row.updated_at).timestamp() if row.updated_at else 0.0,
    }


class BrowserPlaneLockStore:
    def get_lock(self, *, tab_id: str, user_id: int, workspace: str) -> dict[str, Any]:
        clean_tab_id = str(tab_id or "").strip()[:120]
        if not clean_tab_id:
            return {}
        now = datetime.now(timezone.utc)
        db = create_session()
        try:
            row = db.scalar(
                select(BrowserPlaneTabLock)
                .where(
                    BrowserPlaneTabLock.tab_id == clean_tab_id,
                    BrowserPlaneTabLock.user_id == int(user_id),
                    BrowserPlaneTabLock.workspace == _normalize_workspace(workspace),
                )
                .limit(1)
            )
            if row is None:
                return {}
            expires_at = _as_utc_datetime(row.expires_at)
            if expires_at is not None and expires_at <= now:
                db.delete(row)
                db.commit()
                return {}
            return _lock_row_to_payload(row)
        finally:
            db.close()

    def acquire_lock(
        self,
        *,
        tab_id: str,
        user_id: int,
        workspace: str,
        owner: str,
        reason: str = "",
        ttl_seconds: int = 300,
        force: bool = False,
    ) -> dict[str, Any]:
        clean_tab_id = str(tab_id or "").strip()[:120]
        clean_owner = str(owner or "").strip()[:120]
        if not clean_tab_id or not clean_owner:
            return {"ok": False, "error": "invalid_lock_request"}
        normalized_workspace = _normalize_workspace(workspace)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(30, min(3600, int(ttl_seconds or 300))))
        db = create_session()
        try:
            row = db.scalar(
                select(BrowserPlaneTabLock)
                .where(
                    BrowserPlaneTabLock.tab_id == clean_tab_id,
                    BrowserPlaneTabLock.user_id == int(user_id),
                    BrowserPlaneTabLock.workspace == normalized_workspace,
                )
                .limit(1)
            )
            if row is not None:
                current_expires_at = _as_utc_datetime(row.expires_at)
                if current_expires_at is not None and current_expires_at <= now:
                    db.delete(row)
                    db.flush()
                    row = None
            if row is not None and not force and str(row.owner or "") != clean_owner:
                return {"ok": False, "error": "tab_locked", "lock": _lock_row_to_payload(row)}
            if row is None:
                row = BrowserPlaneTabLock(
                    tab_id=clean_tab_id,
                    user_id=int(user_id),
                    workspace=normalized_workspace,
                )
                db.add(row)
            row.owner = clean_owner
            row.reason = str(reason or "")[:255]
            row.expires_at = expires_at
            row.updated_at = now
            db.commit()
            db.refresh(row)
            return {"ok": True, "lock": _lock_row_to_payload(row)}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def release_lock(
        self,
        *,
        tab_id: str,
        user_id: int,
        workspace: str,
        owner: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        clean_tab_id = str(tab_id or "").strip()[:120]
        if not clean_tab_id:
            return {"ok": False, "error": "invalid_tab_id"}
        db = create_session()
        try:
            row = db.scalar(
                select(BrowserPlaneTabLock)
                .where(
                    BrowserPlaneTabLock.tab_id == clean_tab_id,
                    BrowserPlaneTabLock.user_id == int(user_id),
                    BrowserPlaneTabLock.workspace == _normalize_workspace(workspace),
                )
                .limit(1)
            )
            if row is None:
                return {"ok": True, "released": False}
            if not force and str(owner or "").strip() and str(row.owner or "") != str(owner or "").strip():
                return {"ok": False, "error": "tab_lock_owner_mismatch", "lock": _lock_row_to_payload(row)}
            payload = _lock_row_to_payload(row)
            db.delete(row)
            db.commit()
            return {"ok": True, "released": True, "lock": payload}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_locks(self, *, user_id: int, workspace: str) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        db = create_session()
        try:
            rows = list(
                db.scalars(
                    select(BrowserPlaneTabLock)
                    .where(
                        BrowserPlaneTabLock.user_id == int(user_id),
                        BrowserPlaneTabLock.workspace == _normalize_workspace(workspace),
                    )
                    .order_by(BrowserPlaneTabLock.updated_at.desc(), BrowserPlaneTabLock.id.desc())
                )
            )
            payloads: list[dict[str, Any]] = []
            expired_ids: list[int] = []
            for row in rows:
                expires_at = _as_utc_datetime(row.expires_at)
                if expires_at is not None and expires_at <= now:
                    expired_ids.append(int(row.id))
                    continue
                payloads.append(_lock_row_to_payload(row))
            if expired_ids:
                db.execute(delete(BrowserPlaneTabLock).where(BrowserPlaneTabLock.id.in_(expired_ids)))
                db.commit()
            return payloads
        finally:
            db.close()


browser_plane_lock_store = BrowserPlaneLockStore()
