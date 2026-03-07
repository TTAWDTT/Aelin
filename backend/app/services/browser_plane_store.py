from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import create_session
from app.models import BrowserPlaneCheckpoint


def _normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def _safe_json_dumps(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{}"


def _safe_json_loads(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_utc_datetime(value: datetime | None, *, fallback_now: bool = False) -> datetime | None:
    if value is None:
        return datetime.now(timezone.utc) if fallback_now else None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _row_to_payload(row: BrowserPlaneCheckpoint) -> dict[str, Any]:
    created_at = _as_utc_datetime(row.created_at, fallback_now=True) or datetime.fromtimestamp(0, tz=timezone.utc)
    updated_at = _as_utc_datetime(row.updated_at, fallback_now=True) or datetime.fromtimestamp(0, tz=timezone.utc)
    return {
        "request_id": str(row.request_id or ""),
        "profile_id": str(row.profile_id or ""),
        "workspace": str(row.workspace or "default"),
        "domain": str(row.domain or ""),
        "reason": str(row.reason or ""),
        "status": str(row.status or "awaiting_login"),
        "next_call": _safe_json_loads(row.next_call_json or "{}"),
        "resume_query": str(row.resume_query or "")[:500],
        "resume_request": _safe_json_loads(row.resume_request_json or "{}"),
        "continue_after_confirm": bool(row.continue_after_confirm),
        "created_at": created_at.timestamp(),
        "updated_at": updated_at.timestamp(),
    }


class BrowserPlaneStore:
    def upsert_checkpoint(
        self,
        *,
        request_id: str,
        user_id: int,
        workspace: str,
        profile_id: str,
        domain: str,
        reason: str,
        status: str,
        next_call: dict[str, Any] | None,
        resume_query: str,
        resume_request: dict[str, Any] | None,
        continue_after_confirm: bool,
        created_at: float = 0.0,
        updated_at: float = 0.0,
    ) -> dict[str, Any]:
        clean_request_id = str(request_id or "").strip()[:64]
        if not clean_request_id:
            return {}
        normalized_workspace = _normalize_workspace(workspace)
        db = create_session()
        try:
            row = db.scalar(
                select(BrowserPlaneCheckpoint).where(BrowserPlaneCheckpoint.request_id == clean_request_id).limit(1)
            )
            if row is None:
                row = BrowserPlaneCheckpoint(
                    request_id=clean_request_id,
                    user_id=int(user_id),
                    workspace=normalized_workspace,
                )
                db.add(row)
            elif int(row.user_id or 0) != int(user_id) or str(row.workspace or "") != normalized_workspace:
                raise RuntimeError("checkpoint_request_id_collision")
            row.user_id = int(user_id)
            row.workspace = normalized_workspace
            row.profile_id = str(profile_id or "")[:120]
            row.domain = str(domain or "")[:120]
            row.reason = str(reason or "")[:80]
            row.status = str(status or "awaiting_login")[:32]
            row.next_call_json = _safe_json_dumps(next_call or {})
            row.resume_query = str(resume_query or "")[:500]
            row.resume_request_json = _safe_json_dumps(resume_request or {})
            row.continue_after_confirm = bool(continue_after_confirm)
            row_created_at = datetime.fromtimestamp(float(created_at), tz=timezone.utc) if float(created_at or 0.0) > 0 else None
            row_updated_at = datetime.fromtimestamp(float(updated_at), tz=timezone.utc) if float(updated_at or 0.0) > 0 else None
            if row_created_at is not None:
                row.created_at = row_created_at
            if row_updated_at is not None:
                row.updated_at = row_updated_at
            db.commit()
            db.refresh(row)
            return _row_to_payload(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_checkpoint(
        self,
        *,
        request_id: str,
        user_id: int,
        workspace: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        clean_request_id = str(request_id or "").strip()[:64]
        if not clean_request_id:
            return {}
        db = create_session()
        try:
            row = db.scalar(
                select(BrowserPlaneCheckpoint)
                .where(
                    BrowserPlaneCheckpoint.request_id == clean_request_id,
                    BrowserPlaneCheckpoint.user_id == int(user_id),
                    BrowserPlaneCheckpoint.workspace == _normalize_workspace(workspace),
                )
                .limit(1)
            )
            if row is None:
                return {}
            if profile_id and str(row.profile_id or "") != str(profile_id or ""):
                return {}
            return _row_to_payload(row)
        finally:
            db.close()

    def list_checkpoints(
        self,
        *,
        user_id: int,
        workspace: str = "",
        statuses: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        db = create_session()
        try:
            query = select(BrowserPlaneCheckpoint).where(BrowserPlaneCheckpoint.user_id == int(user_id))
            if str(workspace or "").strip():
                query = query.where(BrowserPlaneCheckpoint.workspace == _normalize_workspace(workspace))
            allow_statuses = {
                str(item or "").strip().lower()
                for item in list(statuses or [])
                if str(item or "").strip()
            }
            if allow_statuses:
                query = query.where(BrowserPlaneCheckpoint.status.in_(sorted(allow_statuses)))
            rows = list(
                db.scalars(
                    query.order_by(BrowserPlaneCheckpoint.updated_at.desc(), BrowserPlaneCheckpoint.id.desc()).limit(
                        max(1, min(100, int(limit or 20)))
                    )
                )
            )
            return [_row_to_payload(row) for row in rows]
        finally:
            db.close()

    def update_checkpoint(
        self,
        *,
        request_id: str,
        user_id: int,
        workspace: str,
        profile_id: str = "",
        status: str | None = None,
        resume_query: str | None = None,
        resume_request: dict[str, Any] | None = None,
        continue_after_confirm: bool | None = None,
        next_call: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_request_id = str(request_id or "").strip()[:64]
        if not clean_request_id:
            return {}
        db = create_session()
        try:
            row = db.scalar(
                select(BrowserPlaneCheckpoint)
                .where(
                    BrowserPlaneCheckpoint.request_id == clean_request_id,
                    BrowserPlaneCheckpoint.user_id == int(user_id),
                    BrowserPlaneCheckpoint.workspace == _normalize_workspace(workspace),
                )
                .limit(1)
            )
            if row is None:
                return {}
            if profile_id and str(row.profile_id or "") != str(profile_id or ""):
                return {}
            if status is not None:
                row.status = str(status or row.status)[:32]
            if resume_query is not None and str(resume_query).strip():
                row.resume_query = str(resume_query or "")[:500]
            if isinstance(resume_request, dict):
                row.resume_request_json = _safe_json_dumps(resume_request)
            if continue_after_confirm is not None:
                row.continue_after_confirm = bool(continue_after_confirm)
            if isinstance(next_call, dict):
                row.next_call_json = _safe_json_dumps(next_call)
            row.updated_at = datetime.now(timezone.utc)
            db.add(row)
            db.commit()
            db.refresh(row)
            return _row_to_payload(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


browser_plane_store = BrowserPlaneStore()
