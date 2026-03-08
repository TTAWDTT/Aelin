from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.services.browser_plane_store import browser_plane_store

_LOG = logging.getLogger(__name__)


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


class BrowserAuthGuard:
    def __init__(
        self,
        *,
        login_states: dict[str, BrowserLoginState],
        trusted_auth_domains: dict[tuple[int, str, str], set[str]],
        lock,
    ) -> None:
        self._login_states = login_states
        self._trusted_auth_domains = trusted_auth_domains
        self._lock = lock

    @staticmethod
    def _login_state_payload(state: BrowserLoginState | None) -> dict[str, Any]:
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
            profile_id=str(profile_id or "")[:120],
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
        payload = self._login_state_payload(state)
        try:
            browser_plane_store.upsert_checkpoint(
                request_id=request_id,
                user_id=int(user_id),
                workspace=workspace,
                profile_id=str(profile_id or ""),
                domain=str(domain or ""),
                reason=str(reason or "auth_guard"),
                status="awaiting_login",
                next_call=dict(next_call or {}),
                resume_query=str(resume_query or ""),
                resume_request=dict(resume_request or {}),
                continue_after_confirm=bool(continue_after_confirm),
                created_at=float(now),
                updated_at=float(now),
            )
        except Exception as exc:
            _LOG.warning(
                "browser_plane checkpoint upsert failed request_id=%s workspace=%s error=%s",
                request_id,
                _normalize_workspace(workspace),
                str(exc)[:180],
            )
        return payload

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
            if state is not None:
                if int(state.user_id) != int(user_id) or str(state.workspace or "") != _normalize_workspace(workspace):
                    return {}
                if profile_id and str(state.profile_id or "") != str(profile_id or ""):
                    return {}
                return self._login_state_payload(state)
        try:
            return browser_plane_store.get_checkpoint(
                request_id=clean_request_id,
                user_id=int(user_id),
                workspace=workspace,
                profile_id=profile_id,
            )
        except Exception as exc:
            _LOG.warning(
                "browser_plane checkpoint get failed request_id=%s workspace=%s error=%s",
                clean_request_id,
                _normalize_workspace(workspace),
                str(exc)[:180],
            )
            return {}

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
            if state is not None:
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
                payload = self._login_state_payload(state)
            else:
                payload = {}
        try:
            stored_payload = browser_plane_store.update_checkpoint(
                request_id=clean_request_id,
                user_id=int(user_id),
                workspace=workspace,
                profile_id=profile_id,
                resume_query=str(resume_query or ""),
                resume_request=resume_request if isinstance(resume_request, dict) else None,
                continue_after_confirm=continue_after_confirm,
            )
        except Exception as exc:
            _LOG.warning(
                "browser_plane checkpoint resume update failed request_id=%s workspace=%s error=%s",
                clean_request_id,
                _normalize_workspace(workspace),
                str(exc)[:180],
            )
            stored_payload = {}
        return payload or stored_payload

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
        memory_payloads = [self._login_state_payload(item) for item in rows]
        try:
            stored_payloads = browser_plane_store.list_checkpoints(
                user_id=int(user_id),
                workspace=workspace,
                statuses=list(allow_statuses) if allow_statuses else None,
                limit=max_items,
            )
        except Exception as exc:
            _LOG.warning(
                "browser_plane checkpoint list failed user_id=%s workspace=%s error=%s",
                int(user_id),
                _normalize_workspace(workspace or "default") if str(workspace or "").strip() else "all",
                str(exc)[:180],
            )
            stored_payloads = []
        merged_by_id: dict[str, dict[str, Any]] = {}
        for payload in stored_payloads:
            request_id = str(payload.get("request_id") or "").strip()
            if request_id:
                merged_by_id[request_id] = payload
        for payload in memory_payloads:
            request_id = str(payload.get("request_id") or "").strip()
            if request_id:
                merged_by_id[request_id] = payload
        merged = list(merged_by_id.values())
        merged.sort(
            key=lambda item: float(item.get("updated_at") or item.get("created_at") or 0.0),
            reverse=True,
        )
        return merged[:max_items]

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
            if state is not None:
                if int(state.user_id) != int(user_id) or str(state.workspace or "") != _normalize_workspace(workspace):
                    return {}
                if profile_id and str(state.profile_id or "") != str(profile_id or ""):
                    return {}
                state.touch(status=str(status or "resolved")[:32])
                payload = self._login_state_payload(state)
            else:
                payload = {}
        try:
            stored_payload = browser_plane_store.update_checkpoint(
                request_id=clean_request_id,
                user_id=int(user_id),
                workspace=workspace,
                profile_id=profile_id,
                status=str(status or "resolved")[:32],
            )
        except Exception as exc:
            _LOG.warning(
                "browser_plane checkpoint resolve update failed request_id=%s workspace=%s error=%s",
                clean_request_id,
                _normalize_workspace(workspace),
                str(exc)[:180],
            )
            stored_payload = {}
        resolved = payload or stored_payload
        try:
            domain = str((resolved or {}).get("domain") or "").strip()
            profile_key = str((resolved or {}).get("profile_id") or "").strip()
            resolved_status = str((resolved or {}).get("status") or status or "").strip().lower()
            if domain and profile_key and resolved_status in {"resolved", "continued", "confirmed"}:
                key = (int(user_id), _normalize_workspace(workspace), profile_key)
                with self._lock:
                    trusted = self._trusted_auth_domains.get(key)
                    if trusted is None:
                        trusted = set()
                        self._trusted_auth_domains[key] = trusted
                    trusted.add(domain.lower())
        except Exception:
            pass
        return resolved

