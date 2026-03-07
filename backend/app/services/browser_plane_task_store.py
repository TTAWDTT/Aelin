from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import create_session
from app.models import BrowserPlaneTask


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


def _row_to_payload(row: BrowserPlaneTask) -> dict[str, Any]:
    return {
        "task_id": str(row.task_id or ""),
        "profile_id": str(row.profile_id or ""),
        "tab_id": str(row.tab_id or ""),
        "workspace": str(row.workspace or "default"),
        "kind": str(row.kind or "browser_use"),
        "status": str(row.status or "pending"),
        "scope": str(row.scope or "auto"),
        "action": str(row.action or ""),
        "input": _safe_json_loads(row.input_json or "{}"),
        "result": _safe_json_loads(row.result_json or "{}"),
        "checkpoint_request_id": str(row.checkpoint_request_id or ""),
        "created_at": _as_utc_datetime(row.created_at, fallback_now=True).timestamp() if row.created_at else 0.0,
        "updated_at": _as_utc_datetime(row.updated_at, fallback_now=True).timestamp() if row.updated_at else 0.0,
    }


class BrowserPlaneTaskStore:
    def create_task(
        self,
        *,
        task_id: str,
        user_id: int,
        workspace: str,
        profile_id: str,
        tab_id: str,
        kind: str,
        status: str,
        scope: str,
        action: str,
        input_payload: dict[str, Any] | None,
        result_payload: dict[str, Any] | None = None,
        checkpoint_request_id: str = "",
    ) -> dict[str, Any]:
        clean_task_id = str(task_id or "").strip()[:64]
        if not clean_task_id:
            return {}
        db = create_session()
        try:
            row = BrowserPlaneTask(
                task_id=clean_task_id,
                user_id=int(user_id),
                workspace=_normalize_workspace(workspace),
                profile_id=str(profile_id or "")[:120],
                tab_id=str(tab_id or "")[:120],
                kind=str(kind or "browser_use")[:32],
                status=str(status or "pending")[:32],
                scope=str(scope or "auto")[:24],
                action=str(action or "")[:32],
                input_json=_safe_json_dumps(input_payload or {}),
                result_json=_safe_json_dumps(result_payload or {}),
                checkpoint_request_id=str(checkpoint_request_id or "")[:64],
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return _row_to_payload(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_task(
        self,
        *,
        task_id: str,
        user_id: int,
        workspace: str,
    ) -> dict[str, Any]:
        clean_task_id = str(task_id or "").strip()[:64]
        if not clean_task_id:
            return {}
        db = create_session()
        try:
            row = db.scalar(
                select(BrowserPlaneTask)
                .where(
                    BrowserPlaneTask.task_id == clean_task_id,
                    BrowserPlaneTask.user_id == int(user_id),
                    BrowserPlaneTask.workspace == _normalize_workspace(workspace),
                )
                .limit(1)
            )
            if row is None:
                return {}
            return _row_to_payload(row)
        finally:
            db.close()

    def update_task(
        self,
        *,
        task_id: str,
        user_id: int,
        workspace: str,
        status: str | None = None,
        result_payload: dict[str, Any] | None = None,
        checkpoint_request_id: str | None = None,
        tab_id: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        clean_task_id = str(task_id or "").strip()[:64]
        if not clean_task_id:
            return {}
        db = create_session()
        try:
            row = db.scalar(
                select(BrowserPlaneTask)
                .where(
                    BrowserPlaneTask.task_id == clean_task_id,
                    BrowserPlaneTask.user_id == int(user_id),
                    BrowserPlaneTask.workspace == _normalize_workspace(workspace),
                )
                .limit(1)
            )
            if row is None:
                return {}
            if status is not None:
                row.status = str(status or row.status)[:32]
            if result_payload is not None:
                row.result_json = _safe_json_dumps(result_payload)
            if checkpoint_request_id is not None:
                row.checkpoint_request_id = str(checkpoint_request_id or "")[:64]
            if tab_id is not None:
                row.tab_id = str(tab_id or "")[:120]
            if profile_id is not None:
                row.profile_id = str(profile_id or "")[:120]
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


browser_plane_task_store = BrowserPlaneTaskStore()
