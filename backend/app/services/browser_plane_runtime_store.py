from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.db import create_session
from app.models import BrowserPlaneInstance, BrowserPlaneTab


def _normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def _as_utc_datetime(value: datetime | None, *, fallback_now: bool = False) -> datetime | None:
    if value is None:
        return datetime.now(timezone.utc) if fallback_now else None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _instance_row_to_payload(row: BrowserPlaneInstance) -> dict[str, Any]:
    return {
        "instance_id": str(row.instance_id or ""),
        "profile_id": str(row.profile_id or ""),
        "session_id": str(row.session_id or ""),
        "workspace": str(row.workspace or "default"),
        "mode": str(row.mode or "cdp"),
        "status": str(row.status or "ready"),
        "current_tab_id": str(row.current_tab_id or ""),
        "created_at": _as_utc_datetime(row.created_at, fallback_now=True).timestamp() if row.created_at else 0.0,
        "updated_at": _as_utc_datetime(row.updated_at, fallback_now=True).timestamp() if row.updated_at else 0.0,
    }


def _tab_row_to_payload(row: BrowserPlaneTab) -> dict[str, Any]:
    return {
        "tab_id": str(row.tab_id or ""),
        "instance_id": str(row.instance_id or ""),
        "profile_id": str(row.profile_id or ""),
        "session_id": str(row.session_id or ""),
        "workspace": str(row.workspace or "default"),
        "page_index": int(row.page_index or 0),
        "url": str(row.url or ""),
        "title": str(row.title or ""),
        "is_active": bool(row.is_active),
        "status": str(row.status or "open"),
        "created_at": _as_utc_datetime(row.created_at, fallback_now=True).timestamp() if row.created_at else 0.0,
        "updated_at": _as_utc_datetime(row.updated_at, fallback_now=True).timestamp() if row.updated_at else 0.0,
    }


class BrowserPlaneRuntimeStore:
    def upsert_instance(
        self,
        *,
        instance_id: str,
        user_id: int,
        workspace: str,
        profile_id: str,
        session_id: str,
        mode: str,
        status: str,
        current_tab_id: str = "",
    ) -> dict[str, Any]:
        clean_instance_id = str(instance_id or "").strip()[:96]
        if not clean_instance_id:
            return {}
        db = create_session()
        try:
            row = db.scalar(select(BrowserPlaneInstance).where(BrowserPlaneInstance.instance_id == clean_instance_id).limit(1))
            if row is None:
                row = BrowserPlaneInstance(instance_id=clean_instance_id, user_id=int(user_id), workspace=_normalize_workspace(workspace))
                db.add(row)
            row.user_id = int(user_id)
            row.workspace = _normalize_workspace(workspace)
            row.profile_id = str(profile_id or "")[:120]
            row.session_id = str(session_id or "")[:64]
            row.mode = str(mode or "cdp")[:24]
            row.status = str(status or "ready")[:32]
            row.current_tab_id = str(current_tab_id or "")[:120]
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(row)
            return _instance_row_to_payload(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def replace_tabs_for_instance(
        self,
        *,
        instance_id: str,
        user_id: int,
        workspace: str,
        profile_id: str,
        session_id: str,
        tabs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        clean_instance_id = str(instance_id or "").strip()[:96]
        if not clean_instance_id:
            return []
        db = create_session()
        try:
            db.execute(delete(BrowserPlaneTab).where(BrowserPlaneTab.instance_id == clean_instance_id))
            rows: list[BrowserPlaneTab] = []
            now = datetime.now(timezone.utc)
            for item in list(tabs or []):
                row = BrowserPlaneTab(
                    tab_id=str(item.get("tab_id") or "")[:120],
                    instance_id=clean_instance_id,
                    user_id=int(user_id),
                    workspace=_normalize_workspace(workspace),
                    profile_id=str(profile_id or "")[:120],
                    session_id=str(session_id or "")[:64],
                    page_index=int(item.get("page_index") or 0),
                    url=str(item.get("url") or "")[:4000],
                    title=str(item.get("title") or "")[:255],
                    is_active=bool(item.get("is_active")),
                    status=str(item.get("status") or "open")[:32],
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
                rows.append(row)
            db.commit()
            return [_tab_row_to_payload(row) for row in rows]
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_instances(self, *, user_id: int, workspace: str) -> list[dict[str, Any]]:
        db = create_session()
        try:
            rows = list(
                db.scalars(
                    select(BrowserPlaneInstance)
                    .where(
                        BrowserPlaneInstance.user_id == int(user_id),
                        BrowserPlaneInstance.workspace == _normalize_workspace(workspace),
                    )
                    .order_by(BrowserPlaneInstance.updated_at.desc(), BrowserPlaneInstance.id.desc())
                )
            )
            return [_instance_row_to_payload(row) for row in rows]
        finally:
            db.close()

    def list_tabs(self, *, user_id: int, workspace: str, profile_id: str = "") -> list[dict[str, Any]]:
        db = create_session()
        try:
            query = select(BrowserPlaneTab).where(
                BrowserPlaneTab.user_id == int(user_id),
                BrowserPlaneTab.workspace == _normalize_workspace(workspace),
            )
            if str(profile_id or "").strip():
                query = query.where(BrowserPlaneTab.profile_id == str(profile_id or "").strip())
            rows = list(db.scalars(query.order_by(BrowserPlaneTab.updated_at.desc(), BrowserPlaneTab.id.desc())))
            return [_tab_row_to_payload(row) for row in rows]
        finally:
            db.close()

    def get_tab(self, *, tab_id: str, user_id: int, workspace: str) -> dict[str, Any]:
        clean_tab_id = str(tab_id or "").strip()[:120]
        if not clean_tab_id:
            return {}
        db = create_session()
        try:
            row = db.scalar(
                select(BrowserPlaneTab)
                .where(
                    BrowserPlaneTab.tab_id == clean_tab_id,
                    BrowserPlaneTab.user_id == int(user_id),
                    BrowserPlaneTab.workspace == _normalize_workspace(workspace),
                )
                .limit(1)
            )
            if row is None:
                return {}
            return _tab_row_to_payload(row)
        finally:
            db.close()


browser_plane_runtime_store = BrowserPlaneRuntimeStore()
