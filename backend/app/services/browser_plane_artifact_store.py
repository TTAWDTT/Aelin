from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import create_session
from app.models import BrowserPlaneArtifact


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


def _artifact_row_to_payload(row: BrowserPlaneArtifact) -> dict[str, Any]:
    created_at = row.created_at.astimezone(timezone.utc) if row.created_at and row.created_at.tzinfo else row.created_at
    return {
        "artifact_id": int(row.id or 0),
        "workspace": str(row.workspace or "default"),
        "task_id": str(row.task_id or ""),
        "tab_id": str(row.tab_id or ""),
        "profile_id": str(row.profile_id or ""),
        "kind": str(row.kind or "result"),
        "title": str(row.title or ""),
        "text_content": str(row.text_content or ""),
        "data": _safe_json_loads(row.data_json or "{}"),
        "created_at": created_at.timestamp() if created_at else 0.0,
    }


class BrowserPlaneArtifactStore:
    def create_artifact(
        self,
        *,
        user_id: int,
        workspace: str,
        task_id: str = "",
        tab_id: str = "",
        profile_id: str = "",
        kind: str,
        title: str = "",
        text_content: str = "",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        db = create_session()
        try:
            row = BrowserPlaneArtifact(
                user_id=int(user_id),
                workspace=_normalize_workspace(workspace),
                task_id=str(task_id or "")[:64],
                tab_id=str(tab_id or "")[:120],
                profile_id=str(profile_id or "")[:120],
                kind=str(kind or "result")[:32],
                title=str(title or "")[:255],
                text_content=str(text_content or ""),
                data_json=_safe_json_dumps(data or {}),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return _artifact_row_to_payload(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_artifacts(
        self,
        *,
        user_id: int,
        workspace: str,
        task_id: str = "",
        tab_id: str = "",
        kinds: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        db = create_session()
        try:
            query = select(BrowserPlaneArtifact).where(
                BrowserPlaneArtifact.user_id == int(user_id),
                BrowserPlaneArtifact.workspace == _normalize_workspace(workspace),
            )
            if str(task_id or "").strip():
                query = query.where(BrowserPlaneArtifact.task_id == str(task_id or "").strip()[:64])
            if str(tab_id or "").strip():
                query = query.where(BrowserPlaneArtifact.tab_id == str(tab_id or "").strip()[:120])
            allow_kinds = [str(item or "").strip()[:32] for item in list(kinds or []) if str(item or "").strip()]
            if allow_kinds:
                query = query.where(BrowserPlaneArtifact.kind.in_(allow_kinds))
            rows = list(
                db.scalars(
                    query.order_by(BrowserPlaneArtifact.created_at.desc(), BrowserPlaneArtifact.id.desc()).limit(
                        max(1, min(200, int(limit or 20)))
                    )
                )
            )
            return [_artifact_row_to_payload(row) for row in rows]
        finally:
            db.close()


browser_plane_artifact_store = BrowserPlaneArtifactStore()
