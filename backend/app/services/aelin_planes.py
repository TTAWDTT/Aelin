from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlaneTask, PlaneTaskCheckpoint

_PLANE_TASKS: dict[str, dict[str, Any]] = {}
_PLANE_USER_TASKS: dict[tuple[int, str, str], str] = {}

_ACTIVE_STATES = {"queued", "running", "waiting_user", "blocked"}
_TERMINAL_STATES = {"completed", "failed", "closed"}


def _normalize_workspace(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def _normalize_plane_slug(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split()).lower()
    return clean[:32]


def _normalize_task_id(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return clean[:96]


def _normalize_state(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split()).lower()
    if clean in _ACTIVE_STATES or clean in _TERMINAL_STATES:
        return clean
    return "running" if clean else "queued"


def new_plane_task_id(plane: str) -> str:
    slug = _normalize_plane_slug(plane) or "plane"
    return f"{slug}-task-{uuid4().hex[:12]}"


def plane_catalog_entries() -> list[dict[str, Any]]:
    return [
        {
            "plane": "browser",
            "name": "Browser Plane",
            "backing_system": "PinchTab",
            "summary": "负责网页登录、导航、滚动、抽取页面内容等复杂浏览器任务。",
            "delegation_hint": "复杂网站任务优先整单委派给 browser plane，而不是自己微操浏览器步骤。",
            "when_to_use": [
                "需要登录网站",
                "需要多步导航或滚动加载",
                "需要持续复用同一个网页会话",
            ],
            "actions": ["catalog", "delegate", "status", "continue", "close"],
        }
    ]


def plane_catalog_prompt() -> str:
    return (
        "[AELIN PLANE CATALOG]\n"
        "当前可委派 plane:\n"
        "- browser: 由 PinchTab 支撑，负责复杂浏览器任务（登录、导航、滚动、抽取、持续网页会话）。\n"
        "使用原则：\n"
        "- 对复杂网页任务，优先调用 plane 工具，把高层 goal 委派给 browser plane。\n"
        "- 只有当任务是纯搜索或明显原子时，才优先考虑普通工具。\n"
        "- 一旦已有 browser plane task，优先继续该 task，而不是重新开始。"
    )


def _owner_key(*, user_id: int, workspace: str, plane: str) -> tuple[int, str, str]:
    return int(user_id), _normalize_workspace(workspace), _normalize_plane_slug(plane)


def _json_dumps(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return "{}"


def _json_loads(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def visible_plane_task_payload(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": _normalize_task_id(task_id),
        "plane": _normalize_plane_slug(payload.get("plane") or ""),
        "state": _normalize_state(payload.get("state") or payload.get("status") or ""),
        "summary": str(payload.get("summary") or "")[:260],
        "goal": str(payload.get("goal") or "")[:800],
        "user_prompt": str(payload.get("user_prompt") or "")[:260],
        "requires_user_input": bool(payload.get("requires_user_input")),
        "last_url": str(payload.get("last_url") or "")[:260],
        "last_text": str(payload.get("last_text") or payload.get("last_text_excerpt") or "")[:1200],
    }


def task_belongs_to(task_id: str, payload: dict[str, Any], *, user_id: int, workspace: str, plane: str) -> bool:
    owner = _owner_key(user_id=user_id, workspace=workspace, plane=plane)
    owner_user_id = payload.get("owner_user_id")
    owner_workspace = str(payload.get("owner_workspace") or "")
    owner_plane = str(payload.get("owner_plane") or "")
    try:
        task_owner_user_id = int(owner_user_id)
    except Exception:
        return False
    return (task_owner_user_id, _normalize_workspace(owner_workspace), _normalize_plane_slug(owner_plane)) == owner


def _normalize_payload(payload: dict[str, Any], *, user_id: int, workspace: str, plane: str) -> dict[str, Any]:
    plane_slug = _normalize_plane_slug(plane)
    metadata = payload.get("metadata")
    metadata_json = payload.get("metadata_json")
    if isinstance(metadata, dict):
        encoded_metadata = _json_dumps(metadata)
    elif isinstance(metadata_json, str):
        encoded_metadata = metadata_json
    else:
        encoded_metadata = "{}"
    backing_task_id = str(payload.get("backing_task_id") or payload.get("session_id") or "").strip()[:128]
    instance_id = str(payload.get("instance_id") or "").strip()[:128]
    tab_id = str(payload.get("tab_id") or "").strip()[:128]
    if instance_id or tab_id:
        decoded = _json_loads(encoded_metadata)
        if instance_id:
            decoded["instance_id"] = instance_id
        if tab_id:
            decoded["tab_id"] = tab_id
        encoded_metadata = _json_dumps(decoded)
    return {
        **dict(payload or {}),
        "owner_user_id": int(user_id),
        "owner_workspace": _normalize_workspace(workspace),
        "owner_plane": plane_slug,
        "plane": plane_slug,
        "state": _normalize_state(payload.get("state") or payload.get("status") or ""),
        "goal": str(payload.get("goal") or "")[:800],
        "summary": str(payload.get("summary") or "")[:260],
        "user_prompt": str(payload.get("user_prompt") or "")[:260],
        "requires_user_input": bool(payload.get("requires_user_input")),
        "last_url": str(payload.get("last_url") or "")[:260],
        "last_text": str(payload.get("last_text") or payload.get("last_text_excerpt") or "")[:1200],
        "backing_task_id": backing_task_id,
        "metadata_json": encoded_metadata,
    }


def _store_memory_snapshot(task_id: str, payload: dict[str, Any], *, user_id: int, workspace: str, plane: str) -> None:
    normalized_task_id = _normalize_task_id(task_id)
    if not normalized_task_id:
        return
    stored = _normalize_payload(payload, user_id=user_id, workspace=workspace, plane=plane)
    _PLANE_TASKS[normalized_task_id] = stored
    key = _owner_key(user_id=user_id, workspace=workspace, plane=plane)
    if str(stored.get("state") or "") in _ACTIVE_STATES:
        _PLANE_USER_TASKS[key] = normalized_task_id
    elif _PLANE_USER_TASKS.get(key) == normalized_task_id:
        _PLANE_USER_TASKS.pop(key, None)


def _memory_get_plane_task(task_id: str, *, user_id: int, workspace: str, plane: str) -> dict[str, Any] | None:
    normalized_task_id = _normalize_task_id(task_id)
    if not normalized_task_id:
        return None
    payload = _PLANE_TASKS.get(normalized_task_id)
    if not isinstance(payload, dict):
        return None
    if not task_belongs_to(normalized_task_id, payload, user_id=user_id, workspace=workspace, plane=plane):
        return None
    return payload


def _memory_get_active_plane_task(user_id: int, workspace: str, *, plane: str) -> dict[str, Any] | None:
    key = _owner_key(user_id=user_id, workspace=workspace, plane=plane)
    task_id = _PLANE_USER_TASKS.get(key)
    if not task_id:
        return None
    payload = _PLANE_TASKS.get(task_id)
    if not isinstance(payload, dict):
        return None
    if str(payload.get("state") or "") not in _ACTIVE_STATES:
        return None
    if not task_belongs_to(task_id, payload, user_id=user_id, workspace=workspace, plane=plane):
        return None
    return visible_plane_task_payload(task_id, payload)


def _memory_close_plane_task(task_id: str, *, user_id: int, workspace: str, plane: str) -> None:
    payload = _memory_get_plane_task(task_id, user_id=user_id, workspace=workspace, plane=plane)
    if payload is None:
        return
    payload["state"] = "closed"
    payload["closed_at"] = datetime.now(timezone.utc).isoformat()
    key = _owner_key(user_id=user_id, workspace=workspace, plane=plane)
    if _PLANE_USER_TASKS.get(key) == _normalize_task_id(task_id):
        _PLANE_USER_TASKS.pop(key, None)


def _open_store_session(db: Session | None) -> Session | None:
    if db is None:
        return None
    bind = db.get_bind()
    return Session(bind=bind, autoflush=False, autocommit=False, future=True)


def _checkpoint_kind(payload: dict[str, Any]) -> str:
    prompt = f"{str(payload.get('user_prompt') or '').lower()}\n{str(payload.get('last_url') or '').lower()}"
    if any(token in prompt for token in ("login", "sign in", "log in", "登录", "验证码", "2fa", "challenge")):
        return "login"
    return "manual_review"


def _sync_checkpoint(session: Session, *, task_id: str, payload: dict[str, Any]) -> None:
    open_checkpoints = list(
        session.scalars(
            select(PlaneTaskCheckpoint).where(
                PlaneTaskCheckpoint.task_id == task_id,
                PlaneTaskCheckpoint.status == "open",
            )
        )
    )
    now = datetime.now(timezone.utc)
    if bool(payload.get("requires_user_input")):
        if open_checkpoints:
            checkpoint = open_checkpoints[0]
            checkpoint.kind = _checkpoint_kind(payload)
            checkpoint.prompt = str(payload.get("user_prompt") or "")[:1000]
            checkpoint.metadata_json = _json_dumps(
                {
                    "state": str(payload.get("state") or ""),
                    "last_url": str(payload.get("last_url") or ""),
                }
            )
            return
        session.add(
            PlaneTaskCheckpoint(
                task_id=task_id,
                kind=_checkpoint_kind(payload),
                status="open",
                prompt=str(payload.get("user_prompt") or "")[:1000],
                metadata_json=_json_dumps(
                    {
                        "state": str(payload.get("state") or ""),
                        "last_url": str(payload.get("last_url") or ""),
                    }
                ),
            )
        )
        return

    for checkpoint in open_checkpoints:
        checkpoint.status = "resolved"
        checkpoint.resolved_at = now


def _plane_task_to_payload(row: PlaneTask) -> dict[str, Any]:
    metadata = _json_loads(str(row.metadata_json or "{}"))
    payload = {
        "owner_user_id": int(row.user_id),
        "owner_workspace": str(row.workspace or "default"),
        "owner_plane": str(row.plane or ""),
        "plane": str(row.plane or ""),
        "state": str(row.status or ""),
        "goal": str(row.goal or ""),
        "summary": str(row.summary or ""),
        "user_prompt": str(row.user_prompt or ""),
        "requires_user_input": bool(row.requires_user_input),
        "last_url": str(row.last_url or ""),
        "last_text": str(row.last_text_excerpt or ""),
        "backing_task_id": str(row.backing_task_id or ""),
        "metadata_json": str(row.metadata_json or "{}"),
        "metadata": metadata,
    }
    instance_id = str(metadata.get("instance_id") or "").strip()
    tab_id = str(metadata.get("tab_id") or "").strip()
    if instance_id:
        payload["instance_id"] = instance_id
    if tab_id:
        payload["tab_id"] = tab_id
    return payload


def set_plane_task(
    task_id: str,
    payload: dict[str, Any],
    *,
    user_id: int,
    workspace: str,
    plane: str,
    db: Session | None = None,
) -> None:
    normalized_task_id = _normalize_task_id(task_id)
    if not normalized_task_id:
        return
    stored = _normalize_payload(payload, user_id=user_id, workspace=workspace, plane=plane)
    _store_memory_snapshot(normalized_task_id, stored, user_id=user_id, workspace=workspace, plane=plane)
    store_session = _open_store_session(db)
    if store_session is None:
        return
    try:
        row = store_session.get(PlaneTask, normalized_task_id)
        if row is None:
            row = PlaneTask(id=normalized_task_id, user_id=int(user_id))
            store_session.add(row)
        row.workspace = str(stored.get("owner_workspace") or "default")
        row.plane = str(stored.get("plane") or "")
        row.status = str(stored.get("state") or "queued")
        row.goal = str(stored.get("goal") or "")
        row.summary = str(stored.get("summary") or "")
        row.backing_task_id = str(stored.get("backing_task_id") or "") or None
        row.last_url = str(stored.get("last_url") or "") or None
        row.last_text_excerpt = str(stored.get("last_text") or "")
        row.requires_user_input = bool(stored.get("requires_user_input"))
        row.user_prompt = str(stored.get("user_prompt") or "")
        row.metadata_json = str(stored.get("metadata_json") or "{}")
        row.closed_at = datetime.now(timezone.utc) if row.status == "closed" else None
        _sync_checkpoint(store_session, task_id=normalized_task_id, payload=stored)
        store_session.commit()
    finally:
        store_session.close()


def get_plane_task(
    task_id: str,
    *,
    user_id: int,
    workspace: str,
    plane: str,
    db: Session | None = None,
) -> dict[str, Any] | None:
    store_session = _open_store_session(db)
    if store_session is not None:
        try:
            row = store_session.get(PlaneTask, _normalize_task_id(task_id))
            if row is None:
                return None
            payload = _plane_task_to_payload(row)
            if not task_belongs_to(task_id, payload, user_id=user_id, workspace=workspace, plane=plane):
                return None
            _store_memory_snapshot(task_id, payload, user_id=user_id, workspace=workspace, plane=plane)
            return payload
        finally:
            store_session.close()
    return _memory_get_plane_task(task_id, user_id=user_id, workspace=workspace, plane=plane)


def get_active_plane_task(
    user_id: int,
    workspace: str,
    *,
    plane: str = "browser",
    db: Session | None = None,
) -> dict[str, Any] | None:
    store_session = _open_store_session(db)
    if store_session is not None:
        try:
            row = store_session.scalar(
                select(PlaneTask)
                .where(
                    PlaneTask.user_id == int(user_id),
                    PlaneTask.workspace == _normalize_workspace(workspace),
                    PlaneTask.plane == _normalize_plane_slug(plane),
                    PlaneTask.status.in_(sorted(_ACTIVE_STATES)),
                )
                .order_by(PlaneTask.updated_at.desc(), PlaneTask.created_at.desc())
            )
            if row is None:
                return None
            payload = _plane_task_to_payload(row)
            _store_memory_snapshot(row.id, payload, user_id=user_id, workspace=workspace, plane=plane)
            return visible_plane_task_payload(row.id, payload)
        finally:
            store_session.close()
    return _memory_get_active_plane_task(user_id, workspace, plane=plane)


def close_plane_task(
    task_id: str,
    *,
    user_id: int,
    workspace: str,
    plane: str,
    db: Session | None = None,
) -> None:
    _memory_close_plane_task(task_id, user_id=user_id, workspace=workspace, plane=plane)
    store_session = _open_store_session(db)
    if store_session is None:
        return
    try:
        row = store_session.get(PlaneTask, _normalize_task_id(task_id))
        if row is None:
            return
        payload = _plane_task_to_payload(row)
        if not task_belongs_to(task_id, payload, user_id=user_id, workspace=workspace, plane=plane):
            return
        row.status = "closed"
        row.requires_user_input = False
        row.closed_at = datetime.now(timezone.utc)
        _sync_checkpoint(store_session, task_id=_normalize_task_id(task_id), payload={"requires_user_input": False})
        store_session.commit()
    finally:
        store_session.close()
