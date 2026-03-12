from __future__ import annotations

from typing import Any


_PLANE_TASKS: dict[str, dict[str, Any]] = {}
_PLANE_USER_TASKS: dict[tuple[int, str, str], str] = {}


def _normalize_workspace(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def _normalize_plane_slug(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split()).lower()
    return clean[:32]


def _normalize_task_id(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return clean[:96]


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


def visible_plane_task_payload(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": _normalize_task_id(task_id),
        "plane": _normalize_plane_slug(payload.get("plane") or ""),
        "state": str(payload.get("state") or "")[:32],
        "summary": str(payload.get("summary") or "")[:260],
        "goal": str(payload.get("goal") or "")[:800],
        "user_prompt": str(payload.get("user_prompt") or "")[:260],
        "requires_user_input": bool(payload.get("requires_user_input")),
        "last_url": str(payload.get("last_url") or "")[:260],
        "last_text": str(payload.get("last_text") or "")[:1200],
        "session_id": str(payload.get("session_id") or "")[:128],
        "instance_id": str(payload.get("instance_id") or "")[:128],
        "tab_id": str(payload.get("tab_id") or "")[:128],
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


def set_plane_task(task_id: str, payload: dict[str, Any], *, user_id: int, workspace: str, plane: str) -> None:
    normalized_task_id = _normalize_task_id(task_id)
    if not normalized_task_id:
        return
    plane_slug = _normalize_plane_slug(plane)
    stored = {
        **dict(payload or {}),
        "owner_user_id": int(user_id),
        "owner_workspace": _normalize_workspace(workspace),
        "owner_plane": plane_slug,
        "plane": plane_slug,
    }
    _PLANE_TASKS[normalized_task_id] = stored
    _PLANE_USER_TASKS[_owner_key(user_id=user_id, workspace=workspace, plane=plane_slug)] = normalized_task_id


def get_plane_task(task_id: str, *, user_id: int, workspace: str, plane: str) -> dict[str, Any] | None:
    normalized_task_id = _normalize_task_id(task_id)
    if not normalized_task_id:
        return None
    payload = _PLANE_TASKS.get(normalized_task_id)
    if not isinstance(payload, dict):
        return None
    if not task_belongs_to(normalized_task_id, payload, user_id=user_id, workspace=workspace, plane=plane):
        return None
    return payload


def get_active_plane_task(user_id: int, workspace: str, *, plane: str = "browser") -> dict[str, Any] | None:
    key = _owner_key(user_id=user_id, workspace=workspace, plane=plane)
    task_id = _PLANE_USER_TASKS.get(key)
    if not task_id:
        return None
    payload = _PLANE_TASKS.get(task_id)
    if not isinstance(payload, dict):
        return None
    if not task_belongs_to(task_id, payload, user_id=user_id, workspace=workspace, plane=plane):
        return None
    return visible_plane_task_payload(task_id, payload)


def close_plane_task(task_id: str, *, user_id: int, workspace: str, plane: str) -> None:
    payload = get_plane_task(task_id, user_id=user_id, workspace=workspace, plane=plane)
    if payload is None:
        return
    _PLANE_TASKS.pop(_normalize_task_id(task_id), None)
    key = _owner_key(user_id=user_id, workspace=workspace, plane=plane)
    if _PLANE_USER_TASKS.get(key) == _normalize_task_id(task_id):
        _PLANE_USER_TASKS.pop(key, None)
