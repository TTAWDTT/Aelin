from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.browser_automation import BrowserSession


class BrowserSessionRuntimeMixin:
    def _peek_session(self, *, user_id: int, workspace: str, mode: str, profile_id: str = "") -> BrowserSession | None:
        key = self._session_key(user_id=user_id, workspace=workspace, mode=mode, profile_id=profile_id)
        thread_id = threading.get_ident()
        with self._lock:
            session = self._sessions.get(key)
            if session is None:
                return None
            if int(getattr(session, "owner_thread_id", 0) or 0) != thread_id:
                return None
            return session

    def _set_preferred_scope(self, *, user_id: int, workspace: str, scope: str) -> None:
        normalized = self._normalize_scope(scope)
        if normalized not in {"cdp", "external"}:
            return
        key = self._workspace_scope_key(user_id=user_id, workspace=workspace)
        with self._lock:
            self._preferred_scope_by_workspace[key] = (normalized, time.time())

    def _get_preferred_scope(self, *, user_id: int, workspace: str) -> str:
        key = self._workspace_scope_key(user_id=user_id, workspace=workspace)
        now = time.time()
        with self._lock:
            entry = self._preferred_scope_by_workspace.get(key)
            if entry is None:
                return ""
            scope, ts = entry
            if (now - float(ts or now)) > max(60.0, float(self._idle_ttl_seconds)):
                self._preferred_scope_by_workspace.pop(key, None)
                return ""
            return str(scope or "")

    def _clear_preferred_scope(self, *, user_id: int, workspace: str) -> None:
        key = self._workspace_scope_key(user_id=user_id, workspace=workspace)
        with self._lock:
            self._preferred_scope_by_workspace.pop(key, None)

    def _pop_expired_sessions_locked(self, *, now: float | None = None) -> list[BrowserSession]:
        ts = float(now or time.time())
        expired_sessions: list[BrowserSession] = []
        expired_keys: list[str] = []
        for key, session in self._sessions.items():
            if (ts - float(session.last_used or ts)) > self._idle_ttl_seconds:
                expired_keys.append(key)
        for key in expired_keys:
            session = self._sessions.pop(key, None)
            if session is not None:
                expired_sessions.append(session)
        return expired_sessions

    def _cleanup_idle_sessions(self) -> None:
        with self._lock:
            expired_sessions = self._pop_expired_sessions_locked()
        for session in expired_sessions:
            try:
                session.close()
            except Exception:
                pass

    def _resolve_mode(self, mode: str) -> str:
        raw = str(mode or "").strip().lower()
        if raw in {"managed", "cdp", "system", "all", "auto"}:
            return raw
        default = str(self._mode_default or "auto").strip().lower()
        return default if default in {"managed", "cdp", "auto"} else "auto"

    def _create_session_for_mode(
        self,
        *,
        user_id: int,
        workspace: str,
        mode: str,
        profile_id: str = "",
    ) -> BrowserSession:
        if mode == "cdp":
            self._ensure_cdp_endpoint_ready(user_id=user_id, workspace=workspace, profile_id=profile_id)
            return self._create_cdp_session(
                user_id=user_id,
                workspace=workspace,
                endpoint=self._cdp_endpoint,
                profile_id=profile_id,
            )
        if mode == "managed":
            return self._create_managed_session(user_id=user_id, workspace=workspace, profile_id=profile_id)
        raise RuntimeError(f"unsupported_session_mode:{mode}")

    def _get_session(self, *, user_id: int, workspace: str, mode: str = "auto", profile_id: str = "") -> BrowserSession:
        resolved_mode = self._resolve_mode(mode)
        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        if resolved_mode == "auto":
            if self._cdp_enabled and self._cdp_endpoint:
                try:
                    return self._get_session(
                        user_id=user_id,
                        workspace=workspace,
                        mode="cdp",
                        profile_id=resolved_profile_id,
                    )
                except Exception:
                    pass
            return self._get_session(
                user_id=user_id,
                workspace=workspace,
                mode="managed",
                profile_id=resolved_profile_id,
            )
        if resolved_mode not in {"managed", "cdp"}:
            raise RuntimeError(f"unsupported_session_mode:{resolved_mode}")

        key = self._session_key(
            user_id=user_id,
            workspace=workspace,
            mode=resolved_mode,
            profile_id=resolved_profile_id,
        )
        thread_id = threading.get_ident()
        while True:
            self._cleanup_idle_sessions()
            with self._lock:
                session = self._sessions.get(key)
                if session is not None and int(getattr(session, "owner_thread_id", 0) or 0) != thread_id:
                    try:
                        session.close()
                    finally:
                        self._sessions.pop(key, None)
                    session = None
                if session is not None:
                    session.touch()
                    return session
                creation_lock = self._creation_locks.get(key)
                is_creator = False
                if creation_lock is None:
                    creation_lock = threading.Lock()
                    self._creation_locks[key] = creation_lock
                    is_creator = True

            if not creation_lock:
                continue
            if not is_creator:
                creation_lock.acquire()
                creation_lock.release()
                continue

            creation_lock.acquire()
            created_session: BrowserSession | None = None
            try:
                created_session = self._create_session_for_mode(
                    user_id=user_id,
                    workspace=workspace,
                    mode=resolved_mode,
                    profile_id=resolved_profile_id,
                )
                with self._lock:
                    existing = self._sessions.get(key)
                    if existing is not None and int(getattr(existing, "owner_thread_id", 0) or 0) != thread_id:
                        try:
                            existing.close()
                        finally:
                            self._sessions.pop(key, None)
                        existing = None
                    if existing is None:
                        self._sessions[key] = created_session
                        session_to_use = created_session
                        created_session = None
                    else:
                        session_to_use = existing
                    session_to_use.touch()
                    if self._creation_locks.get(key) is creation_lock:
                        self._creation_locks.pop(key, None)
                    return session_to_use
            finally:
                if created_session is not None:
                    created_session.close()
                creation_lock.release()
                with self._lock:
                    if self._creation_locks.get(key) is creation_lock:
                        self._creation_locks.pop(key, None)
