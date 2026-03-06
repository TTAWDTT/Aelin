from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


def _normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


@dataclass
class BrowserLoginState:
    request_id: str
    profile_id: str
    user_id: int
    workspace: str
    domain: str
    reason: str
    status: str
    next_call: dict[str, Any]
    resume_query: str
    resume_request: dict[str, Any]
    continue_after_confirm: bool
    created_at: float
    updated_at: float

    def touch(self, *, status: str = "") -> None:
        self.updated_at = time.time()
        if status:
            self.status = str(status or self.status)


class BrowserLoginCheckpointService:
    def __init__(self) -> None:
        self._login_states: dict[str, BrowserLoginState] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _payload(state: BrowserLoginState | None) -> dict[str, Any]:
        if state is None:
            return {}
        return {
            "request_id": str(state.request_id or ""),
            "profile_id": str(state.profile_id or ""),
            "workspace": str(state.workspace or "")[:64],
            "domain": str(state.domain or "")[:120],
            "reason": str(state.reason or "")[:80],
            "status": str(state.status or "")[:32],
            "next_call": dict(state.next_call or {}),
            "resume_query": str(state.resume_query or "")[:500],
            "resume_request": dict(state.resume_request or {}),
            "continue_after_confirm": bool(state.continue_after_confirm),
            "created_at": float(state.created_at or 0.0),
            "updated_at": float(state.updated_at or 0.0),
        }

    def mark_login_pending(
        self,
        *,
        user_id: int,
        workspace: str,
        domain: str,
        next_call: dict[str, Any] | None = None,
        profile_id: str = "",
        reason: str = "auth_guard",
        resume_query: str = "",
        resume_request: dict[str, Any] | None = None,
        continue_after_confirm: bool = True,
    ) -> dict[str, Any]:
        request_id = f"blogin-{uuid4().hex[:12]}"
        now = time.time()
        state = BrowserLoginState(
            request_id=request_id,
            profile_id=str(profile_id or "").strip(),
            user_id=int(user_id),
            workspace=_normalize_workspace(workspace),
            domain=str(domain or "")[:120],
            reason=str(reason or "auth_guard")[:80],
            status="awaiting_login",
            next_call=dict(next_call or {}),
            resume_query=str(resume_query or "")[:500],
            resume_request=dict(resume_request or {}),
            continue_after_confirm=bool(continue_after_confirm),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._login_states[request_id] = state
        return self._payload(state)

    def get_login_state(
        self,
        *,
        user_id: int,
        workspace: str,
        request_id: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        clean_request_id = str(request_id or "").strip()
        if not clean_request_id:
            return {}
        with self._lock:
            state = self._login_states.get(clean_request_id)
            if state is None:
                return {}
            if int(state.user_id) != int(user_id) or str(state.workspace or "") != _normalize_workspace(workspace):
                return {}
            if profile_id and str(state.profile_id or "") != str(profile_id or ""):
                return {}
            return self._payload(state)

    def attach_login_resume_context(
        self,
        *,
        user_id: int,
        workspace: str,
        request_id: str,
        profile_id: str = "",
        resume_query: str = "",
        resume_request: dict[str, Any] | None = None,
        continue_after_confirm: bool | None = None,
    ) -> dict[str, Any]:
        clean_request_id = str(request_id or "").strip()
        if not clean_request_id:
            return {}
        with self._lock:
            state = self._login_states.get(clean_request_id)
            if state is None:
                return {}
            if int(state.user_id) != int(user_id) or str(state.workspace or "") != _normalize_workspace(workspace):
                return {}
            if profile_id and str(state.profile_id or "") != str(profile_id or ""):
                return {}
            if str(resume_query or "").strip():
                state.resume_query = str(resume_query or "")[:500]
            if isinstance(resume_request, dict) and resume_request:
                state.resume_request = dict(resume_request)
            if continue_after_confirm is not None:
                state.continue_after_confirm = bool(continue_after_confirm)
            state.touch()
            return self._payload(state)

    def list_login_states(
        self,
        *,
        user_id: int,
        workspace: str = "",
        statuses: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        normalized_workspace = _normalize_workspace(workspace) if str(workspace or "").strip() else ""
        allow_statuses = {
            str(item or "").strip().lower()
            for item in list(statuses or [])
            if str(item or "").strip()
        }
        max_items = max(1, min(100, int(limit or 20)))
        rows: list[BrowserLoginState] = []
        with self._lock:
            for state in self._login_states.values():
                if int(state.user_id) != int(user_id):
                    continue
                if normalized_workspace and str(state.workspace or "") != normalized_workspace:
                    continue
                if allow_statuses and str(state.status or "").strip().lower() not in allow_statuses:
                    continue
                rows.append(state)
        rows.sort(key=lambda item: float(item.updated_at or item.created_at or 0.0), reverse=True)
        return [self._payload(item) for item in rows[:max_items]]

    def cancel_login_pending(
        self,
        *,
        user_id: int,
        workspace: str,
        request_id: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        return self.resolve_login_pending(
            user_id=user_id,
            workspace=workspace,
            request_id=request_id,
            profile_id=profile_id,
            status="cancelled",
        )

    def resolve_login_pending(
        self,
        *,
        user_id: int,
        workspace: str,
        request_id: str,
        profile_id: str = "",
        status: str = "resolved",
    ) -> dict[str, Any]:
        clean_request_id = str(request_id or "").strip()
        if not clean_request_id:
            return {}
        with self._lock:
            state = self._login_states.get(clean_request_id)
            if state is None:
                return {}
            if int(state.user_id) != int(user_id) or str(state.workspace or "") != _normalize_workspace(workspace):
                return {}
            if profile_id and str(state.profile_id or "") != str(profile_id or ""):
                return {}
            state.touch(status=str(status or "resolved")[:32])
            return self._payload(state)


browser_login_checkpoint_service = BrowserLoginCheckpointService()
