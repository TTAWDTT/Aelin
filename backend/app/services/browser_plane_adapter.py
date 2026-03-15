from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.aelin_planes import (
    append_plane_artifact,
    append_plane_event,
    close_plane_task,
    get_plane_task,
    new_plane_task_id,
    set_plane_task,
    visible_plane_task_payload,
)

_BROWSER_PLANE_ACTIVE_STATES = {"queued", "running", "waiting_user", "blocked"}
_STALE_BACKING_TASK_ERRORS = {"unknown_session_id", "plane_missing_session_id"}


def _snapshot_artifact_payload(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("last_text") or "").strip(),
        str(payload.get("last_url") or "").strip(),
    )


def _persist_snapshot_artifacts(
    *,
    task_id: str,
    current_payload: dict[str, Any],
    previous_payload: dict[str, Any] | None,
    user_id: int,
    workspace: str,
    db: Session | None,
) -> None:
    current_text, current_url = _snapshot_artifact_payload(current_payload)
    previous_text, previous_url = _snapshot_artifact_payload(previous_payload or {})

    if current_text and current_text != previous_text:
        append_plane_artifact(
            task_id,
            kind="page_text",
            content={"text": current_text},
            user_id=user_id,
            workspace=workspace,
            plane="browser",
            db=db,
        )
    if current_url and current_url != previous_url:
        append_plane_artifact(
            task_id,
            kind="page_location",
            content={"url": current_url},
            user_id=user_id,
            workspace=workspace,
            plane="browser",
            db=db,
        )


def _browser_plane_state_from_session_result(result: dict[str, Any]) -> str:
    if bool(result.get("requires_user_login")):
        return "waiting_user"
    status = str(result.get("status") or result.get("last_status") or "").strip().lower()
    if status.startswith("error"):
        return "failed"
    if status in {"completed", "done", "closed"}:
        return "completed"
    if status in {"partial", "running", "started", "in_progress"}:
        return "running"
    return "running"


def _browser_plane_payload_from_session_result(
    *,
    goal: str,
    result: dict[str, Any],
    existing_task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = str(result.get("summary") or result.get("last_summary") or "")[:260]
    existing_instance_id = str(existing_task.get("instance_id") or "").strip()[:128] if isinstance(existing_task, dict) else ""
    existing_tab_id = str(existing_task.get("tab_id") or "").strip()[:128] if isinstance(existing_task, dict) else ""
    existing_state = str(existing_task.get("state") or "").strip().lower() if isinstance(existing_task, dict) else ""
    existing_requires_user_input = bool(existing_task.get("requires_user_input")) if isinstance(existing_task, dict) else False
    existing_user_prompt = str(existing_task.get("user_prompt") or "").strip()[:260] if isinstance(existing_task, dict) else ""
    instance_id = str(result.get("instance_id") or existing_instance_id or "").strip()[:128]
    tab_id = str(result.get("tab_id") or existing_tab_id or "").strip()[:128]
    backing_task_id = str(
        result.get("session_id")
        or (existing_task.get("backing_task_id") if isinstance(existing_task, dict) else "")
        or (existing_task.get("session_id") if isinstance(existing_task, dict) else "")
        or ""
    ).strip()[:128]
    has_login_signal = any(key in result for key in ("requires_user_login", "user_prompt"))
    requires_user_input = bool(result.get("requires_user_login"))
    user_prompt = str(result.get("user_prompt") or "").strip()[:260]
    state = _browser_plane_state_from_session_result(result)
    if not has_login_signal and existing_requires_user_input and existing_state == "waiting_user":
        requires_user_input = True
        user_prompt = existing_user_prompt
        state = "waiting_user"
    return {
        "plane": "browser",
        "state": state,
        "summary": summary,
        "goal": str(goal or result.get("last_goal") or "").strip()[:800],
        "user_prompt": user_prompt,
        "requires_user_input": requires_user_input,
        "last_url": str(result.get("last_url") or result.get("url") or "").strip()[:260],
        "last_text": str(result.get("last_text") or result.get("text") or "").strip()[:1200],
        "backing_task_id": backing_task_id,
        "instance_id": instance_id,
        "tab_id": tab_id,
    }


class PinchTabBrowserPlaneAdapter:
    def __init__(
        self,
        *,
        db: Session | None,
        user_id: int,
        workspace: str,
        session_executor: Callable[..., tuple[str, dict[str, Any], str, int]],
    ) -> None:
        self._db = db
        self._user_id = int(user_id)
        self._workspace = str(workspace or "default")
        self._session_executor = session_executor

    def _close_stale_backing_task(
        self,
        *,
        task_id: str,
        task: dict[str, Any],
        action: str,
        error: str,
    ) -> dict[str, Any]:
        close_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db)
        append_plane_event(
            task_id,
            event_type="stale_backing_task",
            from_state=str(task.get("state") or ""),
            to_state="closed",
            summary=f"Backing browser session became unavailable during {action}",
            payload={"action": action, "error": error[:180]},
            user_id=self._user_id,
            workspace=self._workspace,
            plane="browser",
            db=self._db,
        )
        stored = get_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db) or {
            **task,
            "state": "closed",
        }
        visible = visible_plane_task_payload(task_id, stored)
        return {
            "ok": True,
            "closed": True,
            "stale_backing_task": True,
            "stale_error": error[:180],
            **visible,
        }

    def delegate(self, *, goal: str) -> dict[str, Any]:
        status, result, error, latency_ms = self._session_executor(action="start", goal=goal)
        if not bool(result.get("ok")):
            return {"ok": False, "error": str(result.get("error") or error or "plane_delegate_failed")}
        backing_task_id = str(result.get("session_id") or "").strip()
        if not backing_task_id:
            return {"ok": False, "error": "plane_missing_task_backend_id"}
        task_id = new_plane_task_id("browser")
        payload = _browser_plane_payload_from_session_result(goal=goal, result=result)
        set_plane_task(task_id, payload, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db)
        append_plane_event(
            task_id,
            event_type="delegated",
            from_state="queued",
            to_state=str(payload.get("state") or ""),
            summary=str(payload.get("summary") or "") or f"Delegated goal: {goal}"[:500],
            payload={
                "goal": str(goal or "")[:800],
                "session_status": status,
                "latency_ms": latency_ms,
            },
            user_id=self._user_id,
            workspace=self._workspace,
            plane="browser",
            db=self._db,
        )
        _persist_snapshot_artifacts(
            task_id=task_id,
            current_payload=payload,
            previous_payload=None,
            user_id=self._user_id,
            workspace=self._workspace,
            db=self._db,
        )
        stored = get_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db) or payload
        return {"ok": True, "latency_ms": latency_ms, **visible_plane_task_payload(task_id, stored)}

    def status(self, *, task_id: str) -> dict[str, Any]:
        task = get_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db)
        if task is None:
            return {"ok": False, "error": "unknown_task_id"}
        backing_task_id = str(task.get("backing_task_id") or task.get("session_id") or "").strip()
        if not backing_task_id:
            return {"ok": False, "error": "plane_missing_session_id"}
        status, result, error, latency_ms = self._session_executor(action="status", session_id=backing_task_id)
        if not bool(result.get("ok")):
            failure = str(result.get("error") or error or "plane_status_failed")
            if failure in _STALE_BACKING_TASK_ERRORS:
                closed = self._close_stale_backing_task(task_id=task_id, task=task, action="status", error=failure)
                closed["latency_ms"] = latency_ms
                return closed
            return {"ok": False, "error": failure}
        payload = _browser_plane_payload_from_session_result(goal=str(task.get("goal") or ""), result=result, existing_task=task)
        set_plane_task(task_id, payload, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db)
        append_plane_event(
            task_id,
            event_type="status_sync",
            from_state=str(task.get("state") or ""),
            to_state=str(payload.get("state") or ""),
            summary=str(payload.get("summary") or "") or "Status synchronized from backing browser runtime",
            payload={
                "session_status": status,
                "latency_ms": latency_ms,
                "requires_user_input": bool(payload.get("requires_user_input")),
            },
            user_id=self._user_id,
            workspace=self._workspace,
            plane="browser",
            db=self._db,
        )
        _persist_snapshot_artifacts(
            task_id=task_id,
            current_payload=payload,
            previous_payload=task,
            user_id=self._user_id,
            workspace=self._workspace,
            db=self._db,
        )
        stored = get_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db) or payload
        return {"ok": True, "latency_ms": latency_ms, **visible_plane_task_payload(task_id, stored)}

    def continue_task(self, *, task_id: str, goal: str) -> dict[str, Any]:
        task = get_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db)
        if task is None:
            return {"ok": False, "error": "unknown_task_id"}
        next_goal = goal or str(task.get("goal") or "").strip()
        if not next_goal:
            return {"ok": False, "error": "missing goal"}
        backing_task_id = str(task.get("backing_task_id") or task.get("session_id") or "").strip()
        if not backing_task_id:
            return {"ok": False, "error": "plane_missing_session_id"}
        status, result, error, latency_ms = self._session_executor(
            action="step",
            session_id=backing_task_id,
            goal=next_goal,
        )
        if not bool(result.get("ok")):
            failure = str(result.get("error") or error or "plane_continue_failed")
            if failure in _STALE_BACKING_TASK_ERRORS:
                closed = self._close_stale_backing_task(task_id=task_id, task=task, action="continue", error=failure)
                closed["latency_ms"] = latency_ms
                return closed
            return {"ok": False, "error": failure}
        payload = _browser_plane_payload_from_session_result(goal=next_goal, result=result, existing_task=task)
        set_plane_task(task_id, payload, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db)
        append_plane_event(
            task_id,
            event_type="continued",
            from_state=str(task.get("state") or ""),
            to_state=str(payload.get("state") or ""),
            summary=str(payload.get("summary") or "") or f"Continued with goal: {next_goal}"[:500],
            payload={
                "goal": next_goal[:800],
                "session_status": status,
                "latency_ms": latency_ms,
            },
            user_id=self._user_id,
            workspace=self._workspace,
            plane="browser",
            db=self._db,
        )
        _persist_snapshot_artifacts(
            task_id=task_id,
            current_payload=payload,
            previous_payload=task,
            user_id=self._user_id,
            workspace=self._workspace,
            db=self._db,
        )
        stored = get_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db) or payload
        return {"ok": True, "latency_ms": latency_ms, **visible_plane_task_payload(task_id, stored)}

    def close(self, *, task_id: str) -> dict[str, Any]:
        task = get_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db)
        if task is None:
            return {"ok": False, "error": "unknown_task_id"}
        backing_task_id = str(task.get("backing_task_id") or task.get("session_id") or "").strip()
        if backing_task_id:
            self._session_executor(action="close", session_id=backing_task_id)
        close_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db)
        append_plane_event(
            task_id,
            event_type="closed",
            from_state=str(task.get("state") or ""),
            to_state="closed",
            summary="Browser plane task closed",
            payload={
                "backing_task_id": backing_task_id,
            },
            user_id=self._user_id,
            workspace=self._workspace,
            plane="browser",
            db=self._db,
        )
        return {"ok": True, "task_id": task_id, "plane": "browser", "state": "closed", "closed": True}

    def has_active_task(self, *, task_id: str) -> bool:
        task = get_plane_task(task_id, user_id=self._user_id, workspace=self._workspace, plane="browser", db=self._db)
        if not isinstance(task, dict):
            return False
        return str(task.get("state") or "") in _BROWSER_PLANE_ACTIVE_STATES
