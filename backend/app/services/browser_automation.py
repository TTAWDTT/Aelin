from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.settings import settings
from app.services.browser_runtime_cdp_lifecycle import BrowserCdpLifecycleRuntimeMixin
from app.services.browser_runtime_cdp_processes import BrowserCdpProcessRuntimeMixin

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore
    from playwright.sync_api import sync_playwright  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    PlaywrightTimeoutError = RuntimeError
    sync_playwright = None

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None

_RISK_KEYWORDS = (
    "delete",
    "remove",
    "submit",
    "send",
    "confirm",
    "pay",
    "payment",
    "checkout",
    "购买",
    "支付",
    "提交",
    "发送",
    "删除",
    "确认",
)

_SENSITIVE_AUTH_DOMAINS = (
    "github.com",
    "x.com",
    "twitter.com",
    "accounts.google.com",
    "google.com",
    "facebook.com",
    "discord.com",
    "slack.com",
)

_BROWSER_FAMILY_NAMES = {
    "chrome",
    "chrome.exe",
    "msedge",
    "msedge.exe",
    "firefox",
    "firefox.exe",
    "chromium",
    "chromium.exe",
    "opera",
    "opera.exe",
    "brave",
    "brave.exe",
}
_CHROMIUM_FAMILIES = {"chrome", "chromium", "edge", "brave", "opera"}
_BROWSER_NAME_TOKENS = ("chrome", "edge", "firefox", "opera", "brave", "chromium")
_LOG = logging.getLogger(__name__)


def _normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def _clamp_int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        out = int(value)
    except Exception:
        out = int(default)
    return max(int(low), min(int(high), out))


@dataclass
class BrowserSession:
    session_id: str
    user_id: int
    workspace: str
    profile_id: str
    mode: str
    owner_thread_id: int
    playwright: Any
    browser: Any
    context: Any
    page: Any
    created_at: float
    last_used: float
    user_data_dir: str = ""
    lock: threading.RLock = field(default_factory=threading.RLock)

    def touch(self) -> None:
        self.last_used = time.time()

    def close(self) -> None:
        for attr in ("context", "browser", "playwright"):
            item = getattr(self, attr, None)
            if item is None:
                continue
            try:
                closer = None
                if attr == "playwright":
                    closer = getattr(item, "stop", None) or getattr(item, "close", None)
                else:
                    closer = getattr(item, "close", None)
                if callable(closer):
                    closer()
            except Exception:
                pass


@dataclass
class BrowserProfile:
    profile_id: str
    user_id: int
    workspace: str
    label: str
    kind: str
    created_at: float
    last_used: float

    def touch(self) -> None:
        self.last_used = time.time()


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


class BrowserAutomationService(
    BrowserCdpLifecycleRuntimeMixin,
    BrowserCdpProcessRuntimeMixin,
):
    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._profiles: dict[str, BrowserProfile] = {}
        self._login_states: dict[str, BrowserLoginState] = {}
        self._lock = threading.RLock()
        self._creation_locks: dict[str, threading.Lock] = {}
        self._preferred_scope_by_workspace: dict[str, tuple[str, float]] = {}
        self._default_timeout_ms = _clamp_int(
            getattr(settings, "browser_tool_default_timeout_ms", 12000),
            12000,
            low=1500,
            high=120000,
        )
        self._idle_ttl_seconds = _clamp_int(
            getattr(settings, "browser_tool_idle_ttl_seconds", 900),
            900,
            low=60,
            high=7200,
        )
        self._headless = bool(getattr(settings, "browser_tool_headless", True))
        self._open_external_on_navigate = bool(getattr(settings, "browser_tool_open_external_on_navigate", False))
        self._mode_default = str(getattr(settings, "browser_tool_mode_default", "auto") or "auto").strip().lower()
        self._cdp_enabled = bool(getattr(settings, "browser_tool_cdp_enabled", False))
        self._cdp_endpoint = str(getattr(settings, "browser_tool_cdp_endpoint", "http://127.0.0.1:9222") or "").strip()
        self._cdp_auto_launch = bool(getattr(settings, "browser_tool_cdp_auto_launch", True))
        self._cdp_launch_timeout_seconds = float(
            getattr(settings, "browser_tool_cdp_launch_timeout_seconds", 10.0) or 10.0
        )
        self._cdp_browser_path = str(getattr(settings, "browser_tool_cdp_browser_path", "") or "").strip()
        self._cdp_bootstrap_lock = threading.Lock()
        self._profile_root = self._resolve_runtime_path(
            str(getattr(settings, "browser_tool_profile_dir", "./browser_data/agent_browser") or "./browser_data/agent_browser")
        )
        self._profile_root.mkdir(parents=True, exist_ok=True)
        cdp_profile_raw = str(getattr(settings, "browser_tool_cdp_profile_dir", "") or "").strip()
        self._cdp_profile_dir = (
            self._resolve_runtime_path(cdp_profile_raw) if cdp_profile_raw else (self._profile_root / "cdp")
        )
        self._cdp_profile_dir.mkdir(parents=True, exist_ok=True)
        self._system_process_cache_ttl_seconds = float(
            getattr(settings, "browser_tool_system_process_cache_ttl_seconds", 2.0) or 2.0
        )
        self._system_process_cache_lock = threading.RLock()
        self._system_process_cache: dict[tuple[int, bool], tuple[float, list[dict[str, Any]]]] = {}
        self._active_cdp_profile_key = ""
        self._active_cdp_user_data_dir = ""

    @staticmethod
    def _resolve_runtime_path(raw: str) -> Path:
        path = Path(str(raw or "").strip() or ".").expanduser()
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).resolve().parents[2]
        return (backend_dir / path).resolve()

    @staticmethod
    def _session_key(*, user_id: int, workspace: str, mode: str, profile_id: str = "") -> str:
        safe_mode = str(mode or "managed").strip().lower() or "managed"
        safe_profile = (
            str(profile_id or "").strip()
            or BrowserAutomationService._default_profile_id(workspace=_normalize_workspace(workspace))
        )
        return f"{safe_mode}::{int(user_id)}::{_normalize_workspace(workspace)}::{safe_profile}"

    @staticmethod
    def _workspace_scope_key(*, user_id: int, workspace: str) -> str:
        return f"{int(user_id)}::{_normalize_workspace(workspace)}"

    @staticmethod
    def _default_profile_id(*, workspace: str) -> str:
        return f"{_normalize_workspace(workspace)}:default"

    @staticmethod
    def _profile_key(*, user_id: int, workspace: str, profile_id: str) -> str:
        clean_profile = str(profile_id or "").strip() or BrowserAutomationService._default_profile_id(workspace=workspace)
        return f"{int(user_id)}::{_normalize_workspace(workspace)}::{clean_profile}"

    @staticmethod
    def _resolved_profile_id(*, workspace: str, profile_id: str = "") -> str:
        return str(profile_id or "").strip() or BrowserAutomationService._default_profile_id(workspace=workspace)

    @staticmethod
    def _sanitize_profile_segment(value: str, *, default: str = "default") -> str:
        raw = str(value or "").strip()
        if not raw:
            return default
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
        return sanitized[:80] or default

    def _ensure_profile(self, *, user_id: int, workspace: str, profile_id: str = "") -> BrowserProfile:
        normalized_workspace = _normalize_workspace(workspace)
        resolved_profile_id = self._resolved_profile_id(workspace=normalized_workspace, profile_id=profile_id)
        key = self._profile_key(user_id=user_id, workspace=normalized_workspace, profile_id=resolved_profile_id)
        now = time.time()
        with self._lock:
            profile = self._profiles.get(key)
            if profile is None:
                profile = BrowserProfile(
                    profile_id=resolved_profile_id,
                    user_id=int(user_id),
                    workspace=normalized_workspace,
                    label="Default controlled browser",
                    kind="managed_cdp",
                    created_at=now,
                    last_used=now,
                )
                self._profiles[key] = profile
            else:
                profile.touch()
            return profile

    @staticmethod
    def _profile_payload(profile: BrowserProfile | None) -> dict[str, Any]:
        if profile is None:
            return {}
        return {
            "profile_id": str(profile.profile_id or ""),
            "workspace": str(profile.workspace or "")[:64],
            "label": str(profile.label or "")[:80],
            "kind": str(profile.kind or "")[:32],
        }

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
        profile = self._ensure_profile(user_id=user_id, workspace=workspace, profile_id=profile_id)
        request_id = f"blogin-{uuid4().hex[:12]}"
        now = time.time()
        state = BrowserLoginState(
            request_id=request_id,
            profile_id=profile.profile_id,
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
        return self._login_state_payload(state)

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
            return self._login_state_payload(state)

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
            return self._login_state_payload(state)

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
        return [self._login_state_payload(item) for item in rows[:max_items]]

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
            return self._login_state_payload(state)

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

    def _create_managed_session(self, *, user_id: int, workspace: str, profile_id: str = "") -> BrowserSession:
        if sync_playwright is None:
            raise RuntimeError("playwright_unavailable")

        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=self._headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()
        page.set_default_timeout(self._default_timeout_ms)
        now = time.time()
        return BrowserSession(
            session_id=f"bs-{uuid4().hex[:12]}",
            user_id=int(user_id),
            workspace=_normalize_workspace(workspace),
            profile_id=resolved_profile_id,
            mode="managed",
            owner_thread_id=threading.get_ident(),
            playwright=pw,
            browser=browser,
            context=context,
            page=page,
            created_at=now,
            last_used=now,
        )

    def _create_cdp_session(
        self,
        *,
        user_id: int,
        workspace: str,
        endpoint: str,
        profile_id: str = "",
    ) -> BrowserSession:
        if sync_playwright is None:
            raise RuntimeError("playwright_unavailable")
        target = str(endpoint or "").strip()
        if not re.match(r"^https?://", target, flags=re.I):
            raise RuntimeError("cdp_endpoint_invalid")

        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        user_data_dir = self._resolve_cdp_profile_dir(
            user_id=user_id,
            workspace=workspace,
            profile_id=resolved_profile_id,
        )
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(
            target,
            timeout=self._default_timeout_ms,
        )
        context = browser.contexts[0] if list(getattr(browser, "contexts", []) or []) else browser.new_context()
        pages = list(getattr(context, "pages", []) or [])
        page = pages[-1] if pages else context.new_page()
        page.set_default_timeout(self._default_timeout_ms)
        now = time.time()
        return BrowserSession(
            session_id=f"bs-{uuid4().hex[:12]}",
            user_id=int(user_id),
            workspace=_normalize_workspace(workspace),
            profile_id=resolved_profile_id,
            mode="cdp",
            owner_thread_id=threading.get_ident(),
            playwright=pw,
            browser=browser,
            context=context,
            page=page,
            created_at=now,
            last_used=now,
            user_data_dir=str(user_data_dir),
        )

    @staticmethod
    def _parse_cdp_port(endpoint: str) -> int:
        matched = re.match(r"^https?://(?:127\.0\.0\.1|localhost):(\d{2,5})/?$", str(endpoint or "").strip(), flags=re.I)
        if not matched:
            return 0
        try:
            port = int(matched.group(1))
        except Exception:
            return 0
        if port < 1 or port > 65535:
            return 0
        return port

    def _probe_cdp_endpoint(self, endpoint: str, *, timeout_seconds: float = 0.35) -> bool:
        ok, _reason = self._probe_cdp_endpoint_with_reason(endpoint, timeout_seconds=timeout_seconds)
        return bool(ok)

    def _probe_cdp_endpoint_with_reason(
        self, endpoint: str, *, timeout_seconds: float = 0.35
    ) -> tuple[bool, str]:
        target = str(endpoint or "").strip().rstrip("/")
        if not target:
            return False, "endpoint_empty"
        url = f"{target}/json/version"
        try:
            with urllib.request.urlopen(url, timeout=max(0.2, float(timeout_seconds))) as resp:
                status_code = int(getattr(resp, "status", 200) or 200)
                if status_code >= 400:
                    return False, f"http_status_{status_code}"
                payload = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
            if not isinstance(payload, dict):
                return False, "invalid_json_payload"
            websocket_url = str(payload.get("webSocketDebuggerUrl") or "").strip()
            if not websocket_url:
                return False, "missing_websocket_debugger_url"
            return True, "ok"
        except urllib.error.HTTPError as exc:
            return False, f"http_error_{int(getattr(exc, 'code', 0) or 0)}"
        except urllib.error.URLError as exc:
            reason = str(getattr(exc, "reason", "") or "").strip()
            if reason:
                return False, f"url_error:{reason[:80]}"
            return False, "url_error"
        except TimeoutError:
            return False, "timeout"
        except ValueError:
            return False, "invalid_json"
        except Exception:
            return False, "unexpected_exception"

    def _collect_cdp_probe_snapshot(self, endpoint: str, *, timeout_seconds: float = 0.4) -> dict[str, Any]:
        ok, reason = self._probe_cdp_endpoint_with_reason(endpoint, timeout_seconds=timeout_seconds)
        port = self._parse_cdp_port(endpoint)
        listeners = self._list_port_listener_pids(port=port) if port > 0 else []
        return {
            "ok": bool(ok),
            "reason": str(reason or "unknown"),
            "endpoint": str(endpoint or "")[:160],
            "port": int(port),
            "listener_count": len(listeners),
            "listener_pids": [int(pid) for pid in listeners[:8]],
        }

    @staticmethod
    def _select_first_existing_path(candidates: list[str]) -> str:
        seen: set[str] = set()
        for item in candidates:
            norm = str(item or "").strip()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            if Path(norm).exists():
                return norm
        return ""

    def _list_cft_browser_candidates(self) -> list[str]:
        candidates: list[str] = []
        if os.name != "nt":
            return candidates
        local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
        program_files = str(os.environ.get("ProgramFiles") or "").strip()
        program_files_x86 = str(os.environ.get("ProgramFiles(x86)") or "").strip()
        windows_paths = [
            (local_app_data, "Google/Chrome for Testing/Application/chrome.exe"),
            (program_files, "Google/Chrome for Testing/Application/chrome.exe"),
            (program_files_x86, "Google/Chrome for Testing/Application/chrome.exe"),
            (local_app_data, "GoogleChromeLabs/chrome-for-testing/chrome.exe"),
            (program_files, "GoogleChromeLabs/chrome-for-testing/chrome.exe"),
            (program_files_x86, "GoogleChromeLabs/chrome-for-testing/chrome.exe"),
        ]
        for base, suffix in windows_paths:
            if not base:
                continue
            candidates.append(str(Path(base) / suffix))
        return candidates

    def _list_system_browser_candidates(self) -> list[str]:
        candidates: list[str] = []
        for name in ("chrome", "msedge", "chromium", "brave", "brave-browser"):
            resolved = shutil.which(name)
            if resolved:
                candidates.append(str(resolved))

        if os.name == "nt":
            local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
            program_files = str(os.environ.get("ProgramFiles") or "").strip()
            program_files_x86 = str(os.environ.get("ProgramFiles(x86)") or "").strip()
            windows_paths = [
                (local_app_data, "Google/Chrome/Application/chrome.exe"),
                (program_files, "Google/Chrome/Application/chrome.exe"),
                (program_files_x86, "Google/Chrome/Application/chrome.exe"),
                (local_app_data, "Microsoft/Edge/Application/msedge.exe"),
                (program_files, "Microsoft/Edge/Application/msedge.exe"),
                (program_files_x86, "Microsoft/Edge/Application/msedge.exe"),
            ]
            for base, suffix in windows_paths:
                if not base:
                    continue
                candidates.append(str(Path(base) / suffix))
        return candidates

    def _resolve_cdp_browser_executable(self) -> str:
        configured = str(self._cdp_browser_path or "").strip()
        if configured:
            candidate = Path(configured).expanduser()
            if candidate.exists():
                return str(candidate)
        cft = self._select_first_existing_path(self._list_cft_browser_candidates())
        if cft:
            return cft
        return self._select_first_existing_path(self._list_system_browser_candidates())

    def _resolve_cdp_profile_dir(self, *, user_id: int, workspace: str, profile_id: str = "") -> Path:
        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        normalized_workspace = _normalize_workspace(workspace)
        user_segment = f"user_{int(user_id)}"
        workspace_segment = self._sanitize_profile_segment(normalized_workspace, default="default")
        profile_segment = self._sanitize_profile_segment(resolved_profile_id, default="default")
        target = self._cdp_profile_dir / user_segment / workspace_segment / profile_segment
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _normalize_path_value(path: str | Path | None) -> str:
        raw = str(path or "").strip()
        if not raw:
            return ""
        try:
            return str(Path(raw).resolve())
        except Exception:
            return str(Path(raw))

    @staticmethod
    def _extract_user_data_dir_from_cmdline(cmdline: str) -> str:
        text = str(cmdline or "").strip()
        if not text:
            return ""
        patterns = (
            r'--user-data-dir="([^"]+)"',
            r"--user-data-dir=([^\s]+)",
            r'--user-data-dir\s+"([^"]+)"',
            r"--user-data-dir\s+([^\s]+)",
        )
        for pattern in patterns:
            matched = re.search(pattern, text, flags=re.I)
            if matched:
                return str(matched.group(1) or "").strip().strip('"')
        return ""

    def _get_cdp_listener_user_data_dir(self, *, endpoint: str) -> str:
        conflicts = self._list_cdp_conflict_processes(max_items=8, endpoint=endpoint)
        for row in conflicts:
            cmdline = str(row.get("cmdline") or "")
            user_data_dir = self._extract_user_data_dir_from_cmdline(cmdline)
            normalized = self._normalize_path_value(user_data_dir)
            if normalized:
                return normalized
        return ""

    def _remember_active_cdp_profile(
        self,
        *,
        user_id: int,
        workspace: str,
        profile_id: str = "",
        user_data_dir: str = "",
    ) -> None:
        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        profile_key = self._profile_key(user_id=user_id, workspace=workspace, profile_id=resolved_profile_id)
        with self._lock:
            self._active_cdp_profile_key = profile_key
            self._active_cdp_user_data_dir = self._normalize_path_value(user_data_dir)

    def _clear_active_cdp_profile(self) -> None:
        with self._lock:
            self._active_cdp_profile_key = ""
            self._active_cdp_user_data_dir = ""

    def _is_target_cdp_profile_active(self, *, user_id: int, workspace: str, profile_id: str = "") -> bool:
        target_dir = self._normalize_path_value(
            self._resolve_cdp_profile_dir(user_id=user_id, workspace=workspace, profile_id=profile_id)
        )
        if not target_dir:
            return False
        active_dir = self._get_cdp_listener_user_data_dir(endpoint=self._cdp_endpoint)
        if active_dir:
            return active_dir == target_dir
        target_profile_key = self._profile_key(
            user_id=user_id,
            workspace=workspace,
            profile_id=self._resolved_profile_id(workspace=workspace, profile_id=profile_id),
        )
        with self._lock:
            remembered_key = str(self._active_cdp_profile_key or "")
            remembered_dir = str(self._active_cdp_user_data_dir or "")
        if remembered_dir:
            return self._normalize_path_value(remembered_dir) == target_dir
        return bool(remembered_key) and remembered_key == target_profile_key

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
                    return self._get_session(user_id=user_id, workspace=workspace, mode="cdp", profile_id=resolved_profile_id)
                except Exception:
                    pass
            return self._get_session(user_id=user_id, workspace=workspace, mode="managed", profile_id=resolved_profile_id)
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

    @staticmethod
    def _is_selector_like(target: str) -> bool:
        value = str(target or "").strip()
        if not value:
            return False
        return value.startswith(("#", ".", "[", "//", "xpath=", "css=")) or any(
            token in value for token in (">", ":", "=", "(", ")")
        )

    @staticmethod
    def _is_high_risk(action: str, *, target: str = "", value: str = "", url: str = "") -> bool:
        corpus = " ".join(
            (
                str(action or ""),
                str(target or ""),
                str(value or ""),
                str(url or ""),
            )
        ).lower()
        return any(token in corpus for token in _RISK_KEYWORDS)

    @staticmethod
    def _open_external_url(url: str) -> bool:
        target = str(url or "").strip()
        if not re.match(r"^https?://", target, flags=re.I):
            return False
        try:
            return bool(webbrowser.open_new_tab(target))
        except Exception:
            return False

    @staticmethod
    def _extract_hostname(url: str) -> str:
        text = str(url or "").strip()
        if not text:
            return ""
        matched = re.match(r"^https?://([^/:?#]+)", text, flags=re.I)
        if not matched:
            return ""
        return str(matched.group(1) or "").strip().lower()

    @classmethod
    def _is_sensitive_auth_domain(cls, url: str) -> bool:
        host = cls._extract_hostname(url)
        if not host:
            return False
        return any(host == d or host.endswith(f".{d}") for d in _SENSITIVE_AUTH_DOMAINS)

    @staticmethod
    def _normalize_scope(scope: str) -> str:
        raw = str(scope or "").strip().lower()
        if raw in {"managed", "cdp", "system", "all", "auto", "external"}:
            return raw
        return "auto"

    @staticmethod
    def _guess_browser_family(name: str, exe: str, cmdline: str) -> str:
        blob = " ".join([str(name or "").lower(), str(exe or "").lower(), str(cmdline or "").lower()])
        if "msedge" in blob or "edge" in blob:
            return "edge"
        if "firefox" in blob:
            return "firefox"
        if "brave" in blob:
            return "brave"
        if "opera" in blob:
            return "opera"
        if "chromium" in blob:
            return "chromium"
        if "chrome" in blob:
            return "chrome"
        return "unknown"

    @staticmethod
    def _is_browser_name(name: str) -> bool:
        low_name = str(name or "").strip().lower()
        if not low_name:
            return False
        if low_name in _BROWSER_FAMILY_NAMES:
            return True
        return any(token in low_name for token in _BROWSER_NAME_TOKENS)

    @staticmethod
    def _is_chromium_name(name: str) -> bool:
        low_name = str(name or "").strip().lower()
        if not low_name:
            return False
        if "msedge" in low_name or "edge" in low_name:
            return True
        return any(token in low_name for token in ("chrome", "chromium", "brave", "opera"))

    def _collect_browser_pids(self, *, pid: int = 0) -> list[dict[str, Any]]:
        if psutil is None:
            return []
        out: list[dict[str, Any]] = []
        for proc in psutil.process_iter(attrs=["pid", "name"]):
            try:
                info = proc.info if isinstance(getattr(proc, "info", None), dict) else {}
                proc_pid = int(info.get("pid") or 0)
                if proc_pid <= 0:
                    continue
                if pid > 0 and proc_pid != int(pid):
                    continue
                name = str(info.get("name") or "").strip()
                if not self._is_browser_name(name):
                    continue
                out.append(
                    {
                        "pid": proc_pid,
                        "name": name[:80],
                        "browser_family": self._guess_browser_family(name, "", ""),
                        "status": "",
                        "started_at": 0.0,
                        "memory_mb": 0.0,
                        "exe": "",
                        "cmdline": "",
                    }
                )
            except Exception:
                continue
        return out

    def _fill_process_details(self, rows: list[dict[str, Any]], *, max_probe: int) -> None:
        if psutil is None or not rows:
            return
        probe_limit = max(0, int(max_probe or 0))
        if probe_limit <= 0:
            return
        for row in rows[:probe_limit]:
            try:
                proc = psutil.Process(int(row.get("pid") or 0))
            except Exception:
                continue
            try:
                exe = str(proc.exe() or "").strip()
            except Exception:
                exe = ""
            try:
                cmdline = " ".join([str(part) for part in (proc.cmdline() or []) if str(part or "").strip()]).strip()
            except Exception:
                cmdline = ""
            try:
                rss = int(getattr(proc.memory_info(), "rss", 0) or 0)
            except Exception:
                rss = 0
            if exe:
                row["exe"] = exe[:260]
            if cmdline:
                row["cmdline"] = cmdline[:600]
            row["memory_mb"] = round(rss / (1024 * 1024), 2) if rss > 0 else 0.0
            if str(row.get("browser_family") or "") in {"", "unknown"}:
                row["browser_family"] = self._guess_browser_family(str(row.get("name") or ""), exe, cmdline)

    def _list_system_browser_processes(
        self,
        *,
        max_items: int,
        pid: int = 0,
        include_details: bool = False,
    ) -> list[dict[str, Any]]:
        if psutil is None:
            return []
        raw_limit = 20 if max_items is None else int(max_items)
        limit = max(0, min(200, raw_limit))
        if limit <= 0:
            return []
        cache_key = (int(pid or 0), bool(include_details))
        now = time.time()
        with self._system_process_cache_lock:
            cached = self._system_process_cache.get(cache_key)
        if cached:
            ts, payload = cached
            if (now - float(ts)) <= max(0.2, float(self._system_process_cache_ttl_seconds)):
                return list(payload)[:limit]

        rows = self._collect_browser_pids(pid=int(pid or 0))
        if include_details:
            self._fill_process_details(rows, max_probe=min(limit, 8))
        rows.sort(key=lambda it: (float(it.get("memory_mb") or 0.0), int(it.get("pid") or 0)), reverse=True)
        trimmed = rows[:limit]
        with self._system_process_cache_lock:
            self._system_process_cache[cache_key] = (now, list(trimmed))
        return trimmed

    def _has_system_browser_process(self, *, pid: int = 0) -> bool:
        if psutil is None:
            return False
        target_pid = int(pid or 0)
        for proc in psutil.process_iter(attrs=["pid", "name"]):
            try:
                info = proc.info if isinstance(getattr(proc, "info", None), dict) else {}
                proc_pid = int(info.get("pid") or 0)
                if proc_pid <= 0:
                    continue
                if target_pid > 0 and proc_pid != target_pid:
                    continue
                if self._is_browser_name(str(info.get("name") or "")):
                    return True
            except Exception:
                continue
        return False

    def _has_reusable_cdp_session(self, *, user_id: int, workspace: str, profile_id: str = "") -> bool:
        session = self._peek_session(user_id=user_id, workspace=workspace, mode="cdp", profile_id=profile_id)
        if session is None:
            return False
        try:
            page = getattr(session, "page", None)
            if page is None:
                return False
            _ = str(getattr(page, "url", "") or "")
            return True
        except Exception:
            return False

    @staticmethod
    def _is_cdp_conflict_row(row: dict[str, Any]) -> bool:
        family = str(row.get("browser_family") or "").strip().lower()
        if family in _CHROMIUM_FAMILIES:
            return True
        blob = " ".join(
            [
                str(row.get("name") or "").lower(),
                str(row.get("exe") or "").lower(),
                str(row.get("cmdline") or "").lower(),
            ]
        )
        return any(token in blob for token in ("chrome", "chromium", "msedge", "edge", "brave", "opera"))

    @staticmethod
    def _extract_connection_port(laddr: Any) -> int:
        if laddr is None:
            return 0
        try:
            if hasattr(laddr, "port"):
                return int(getattr(laddr, "port") or 0)
        except Exception:
            pass
        try:
            if isinstance(laddr, (tuple, list)) and len(laddr) >= 2:
                return int(laddr[1] or 0)
        except Exception:
            pass
        return 0

    def _terminate_processes(self, pids: list[int], *, wait_timeout_seconds: float = 4.0) -> dict[str, Any]:
        safe_pids = sorted({int(pid) for pid in pids if int(pid) > 0 and int(pid) != os.getpid()})
        if not safe_pids:
            return {"terminated_pids": [], "killed_pids": [], "failed_pids": []}
        if psutil is None:
            return {"terminated_pids": [], "killed_pids": [], "failed_pids": safe_pids}

        terminated: list[int] = []
        killed: list[int] = []
        failed: list[int] = []
        processes: list[Any] = []

        for pid in safe_pids:
            try:
                proc = psutil.Process(pid)
            except Exception:
                continue
            try:
                proc.terminate()
                processes.append(proc)
                terminated.append(pid)
            except Exception:
                failed.append(pid)

        if processes:
            try:
                _, alive = psutil.wait_procs(processes, timeout=max(0.5, float(wait_timeout_seconds)))
            except Exception:
                alive = processes
            for proc in alive:
                try:
                    proc.kill()
                    killed.append(int(getattr(proc, "pid", 0) or 0))
                except Exception:
                    failed.append(int(getattr(proc, "pid", 0) or 0))

        return {
            "terminated_pids": sorted({pid for pid in terminated if pid > 0}),
            "killed_pids": sorted({pid for pid in killed if pid > 0}),
            "failed_pids": sorted({pid for pid in failed if pid > 0}),
        }

    @staticmethod
    def _is_complex_auto_action(action: str) -> bool:
        return str(action or "").strip().lower() in {"click", "type", "scroll", "wait"}

    def list_sessions(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str = "all",
        max_items: int = 20,
        pid: int = 0,
    ) -> dict[str, Any]:
        normalized_scope = self._normalize_scope(scope)
        raw_limit = 20 if max_items is None else int(max_items)
        limit = max(0, min(200, raw_limit))
        normalized_workspace = _normalize_workspace(workspace)
        out: dict[str, Any] = {
            "ok": True,
            "scope": normalized_scope,
            "workspace": normalized_workspace,
            "managed_sessions": [],
            "system_processes": [],
            "cdp_enabled": bool(self._cdp_enabled),
            "cdp_endpoint": str(self._cdp_endpoint or ""),
        }
        include_managed = normalized_scope in {"managed", "all", "auto", "cdp"}
        include_system = normalized_scope in {"system", "all", "external"}

        if include_managed:
            self._cleanup_idle_sessions()
            with self._lock:
                for session in self._sessions.values():
                    if int(getattr(session, "user_id", 0) or 0) != int(user_id):
                        continue
                    if str(getattr(session, "workspace", "") or "") != normalized_workspace:
                        continue
                    out["managed_sessions"].append(
                        {
                            "session_id": str(getattr(session, "session_id", "") or ""),
                            "mode": str(getattr(session, "mode", "managed") or "managed"),
                            "profile_id": str(getattr(session, "profile_id", "") or ""),
                            "user_data_dir": str(getattr(session, "user_data_dir", "") or "")[:220],
                            "last_used": float(getattr(session, "last_used", 0.0) or 0.0),
                            "created_at": float(getattr(session, "created_at", 0.0) or 0.0),
                            "owner_thread_id": int(getattr(session, "owner_thread_id", 0) or 0),
                        }
                    )
            managed_sorted = sorted(
                list(out["managed_sessions"]),
                key=lambda it: float(it.get("last_used") or 0.0),
                reverse=True,
            )
            out["managed_sessions"] = managed_sorted[:limit] if limit > 0 else []

        if include_system and limit > 0:
            out["system_processes"] = self._list_system_browser_processes(
                max_items=limit,
                pid=int(pid or 0),
                include_details=False,
            )
        return out

    def _snapshot_page(
        self,
        *,
        page: Any,
        mode: str,
        include_dom: bool,
        include_a11y: bool,
        max_targets: int,
    ) -> dict[str, Any]:
        title = ""
        try:
            title = str(page.title() or "").strip()[:180]
        except Exception:
            title = ""

        url = str(getattr(page, "url", "") or "").strip()[:800]
        ready_state = ""
        try:
            ready_state = str(page.evaluate("() => document.readyState") or "").strip()[:40]
        except Exception:
            ready_state = ""

        interactive_targets: list[dict[str, Any]] = []
        if include_dom:
            script = """
() => {
  const nodes = Array.from(
    document.querySelectorAll(
      'a[href],button,input,textarea,select,[role=\"button\"],[role=\"link\"],[contenteditable=\"true\"],[onclick]'
    )
  );
  const out = [];
  for (const node of nodes) {
    if (out.length >= 60) break;
    const style = window.getComputedStyle(node);
    const hidden = style.display === 'none' || style.visibility === 'hidden';
    if (hidden) continue;
    const rect = node.getBoundingClientRect();
    if (!rect || rect.width < 2 || rect.height < 2) continue;
    const tag = String((node.tagName || '').toLowerCase());
    const role = String(node.getAttribute('role') || '').trim().toLowerCase();
    const id = String(node.id || '').trim();
    const name = String(node.getAttribute('name') || '').trim();
    const aria = String(node.getAttribute('aria-label') || '').trim();
    const text = String(
      aria
      || node.innerText
      || node.textContent
      || node.getAttribute('value')
      || node.getAttribute('placeholder')
      || ''
    ).replace(/\\s+/g, ' ').trim();
    let hint = '';
    if (id) hint = `#${id}`;
    else if (name) hint = `${tag}[name=\"${name}\"]`;
    else if (aria) hint = `${tag}[aria-label=\"${aria}\"]`;
    out.push({ tag, role, text, selector_hint: hint, x: Math.round(rect.x), y: Math.round(rect.y) });
  }
  return out;
}
"""
            try:
                raw_targets = page.evaluate(script) or []
            except Exception:
                raw_targets = []
            if isinstance(raw_targets, list):
                for item in raw_targets[:max_targets]:
                    if not isinstance(item, dict):
                        continue
                    interactive_targets.append(
                        {
                            "tag": str(item.get("tag") or "")[:24],
                            "role": str(item.get("role") or "")[:24],
                            "text": str(item.get("text") or "")[:120],
                            "selector_hint": str(item.get("selector_hint") or "")[:120],
                            "x": _clamp_int(item.get("x"), 0, low=-50000, high=50000),
                            "y": _clamp_int(item.get("y"), 0, low=-50000, high=50000),
                        }
                    )

        a11y_nodes: list[dict[str, Any]] = []
        if include_a11y:
            try:
                snapshot = page.accessibility.snapshot(interesting_only=True)
            except Exception:
                snapshot = None
            if isinstance(snapshot, dict):
                queue = [snapshot]
                while queue and len(a11y_nodes) < 40:
                    node = queue.pop(0)
                    if not isinstance(node, dict):
                        continue
                    role = str(node.get("role") or "").strip()
                    name = str(node.get("name") or "").strip()
                    if role or name:
                        a11y_nodes.append({"role": role[:40], "name": name[:120]})
                    children = node.get("children")
                    if isinstance(children, list):
                        queue.extend([child for child in children if isinstance(child, dict)])

        digest = {
            "interactive_count": len(interactive_targets),
            "a11y_count": len(a11y_nodes),
            "ready_state": ready_state,
        }
        is_blank_page = bool(url.lower().startswith("about:blank"))
        mode_tag = str(mode or "managed").strip().lower() or "managed"
        visibility = "headless" if (mode_tag == "managed" and self._headless) else "visible_window"
        if mode_tag == "cdp":
            scope_note = "这是通过 CDP 接入的用户浏览器会话状态。"
        elif is_blank_page:
            scope_note = "这是 Aelin agent 的浏览器会话，不是系统当前前台浏览器标签页。"
        else:
            scope_note = "这是 Aelin agent 的浏览器会话状态。"
        return {
            "session_scope": mode_tag,
            "is_blank_page": is_blank_page,
            "visibility": visibility,
            "scope_note": scope_note,
            "url": url,
            "title": title,
            "ready_state": ready_state,
            "interactive_targets": interactive_targets,
            "a11y_nodes": a11y_nodes,
            "dom_digest": digest,
        }

    @staticmethod
    def _error_payload(
        *,
        error: str,
        scope: str = "",
        action: str = "",
        requires_cdp: bool = False,
        hint: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": str(error or "unknown_error")[:180],
        }
        if scope:
            payload["scope"] = str(scope)[:24]
        if action:
            payload["action"] = str(action)[:24]
        if requires_cdp:
            payload["requires_cdp"] = True
        if hint:
            payload["hint"] = str(hint)[:220]
        return payload

    def _system_scope_payload(self, *, scope: str, proc_limit: int, pid: int) -> dict[str, Any]:
        if proc_limit <= 0:
            return {
                "ok": True,
                "scope": scope,
                "system_processes": [],
                "scope_note": (
                    "系统浏览器进程视图（fast path，未枚举进程详情）。"
                    if scope == "system"
                    else "external scope fast path：未枚举系统进程详情。"
                ),
            }
        return {
            "ok": True,
            "scope": scope,
            "system_processes": self._list_system_browser_processes(
                max_items=proc_limit,
                pid=int(pid or 0),
                include_details=False,
            ),
            "scope_note": (
                "系统浏览器进程视图（不保证可获得每个标签页 URL）。"
                if scope == "system"
                else "external scope 仅能读取系统浏览器进程级状态，无法直接读取 DOM。"
            ),
        }

    def _resolve_state_runtime_scope(
        self,
        *,
        user_scope: str,
        include_dom: bool,
        include_a11y: bool,
        proc_limit: int,
        pid: int,
    ) -> tuple[str, str, dict[str, Any] | None]:
        if user_scope == "system":
            return user_scope, "", self._system_scope_payload(scope=user_scope, proc_limit=proc_limit, pid=pid)
        if user_scope == "external":
            if include_dom or include_a11y:
                return "", "", self._error_payload(
                    error="external_scope_requires_cdp_for_dom",
                    scope="external",
                    requires_cdp=True,
                    hint="external scope 不支持 DOM/A11y 读取，请改用 scope=auto 或 scope=cdp。",
                )
            return user_scope, "", self._system_scope_payload(scope=user_scope, proc_limit=proc_limit, pid=pid)

        if user_scope == "managed":
            return "", "", self._error_payload(
                error="managed_scope_soft_deleted",
                scope="managed",
                hint="managed 已软下线，请改用 scope=cdp 或 scope=external。",
            )

        if user_scope == "cdp":
            if not self._cdp_enabled:
                return "", "cdp_disabled", self._error_payload(
                    error="cdp_disabled",
                    scope="cdp",
                    requires_cdp=True,
                    hint="当前未启用受控浏览器（CDP），请先启用后再重试。",
                )
            if not self._cdp_endpoint:
                return "", "cdp_endpoint_unconfigured", self._error_payload(
                    error="cdp_endpoint_unconfigured",
                    scope="cdp",
                    requires_cdp=True,
                    hint="当前未配置 CDP 端点，请先完成配置后再重试。",
                )
            return "cdp", "", None

        if user_scope != "auto":
            return "", "", self._error_payload(error=f"unsupported_scope:{user_scope}", scope=user_scope)

        cdp_reachable = bool(
            self._cdp_enabled
            and self._cdp_endpoint
            and self._probe_cdp_endpoint(self._cdp_endpoint, timeout_seconds=0.25)
        )
        if cdp_reachable:
            return "cdp", "", None

        if include_dom or include_a11y:
            if not self._cdp_enabled and not self._cdp_endpoint:
                return "", "cdp_endpoint_unconfigured", self._error_payload(
                    error="cdp_endpoint_unconfigured",
                    scope="auto",
                    requires_cdp=True,
                    hint="当前已软下线 managed；请配置 CDP 端点后重试。",
                )
            if not self._cdp_enabled:
                return "", "cdp_disabled", self._error_payload(
                    error="cdp_disabled",
                    scope="auto",
                    requires_cdp=True,
                    hint="DOM/A11y 读取需要受控浏览器（CDP），当前未启用。",
                )
            if not self._cdp_endpoint:
                return "", "cdp_endpoint_unconfigured", self._error_payload(
                    error="cdp_endpoint_unconfigured",
                    scope="auto",
                    requires_cdp=True,
                    hint="当前已软下线 managed；请配置 CDP 端点后重试。",
                )
            # DOM/A11y 读取必须走 CDP，auto 模式下即使 probe 失败也先尝试一次 CDP bootstrap。
            return "cdp", "", None

        if not self._cdp_enabled:
            fallback_reason = "cdp_disabled" if self._cdp_endpoint else "cdp_endpoint_unconfigured"
        else:
            fallback_reason = "cdp_probe_failed" if self._cdp_endpoint else "cdp_endpoint_unconfigured"
        if not include_dom and not include_a11y and proc_limit <= 0:
            fast_payload = {
                "ok": True,
                "scope": "external",
                "system_processes": [],
                "scope_note": "CDP 暂不可用，fast path 已返回 external 轻量状态。",
            }
            if fallback_reason:
                fast_payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
            return "", fallback_reason, fast_payload

        system_processes = self._list_system_browser_processes(
            max_items=proc_limit,
            pid=int(pid or 0),
            include_details=False,
        )
        if system_processes:
            payload = {
                "ok": True,
                "scope": "external",
                "system_processes": system_processes,
                "scope_note": "检测到用户浏览器正在运行；当前为进程级状态读取，若需 DOM 级读取请启用 CDP。",
            }
            if self._cdp_endpoint:
                payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
            return "", fallback_reason, payload

        if not self._cdp_endpoint:
            return "", fallback_reason, self._error_payload(
                error="cdp_endpoint_unconfigured",
                scope="auto",
                requires_cdp=True,
                hint="当前已软下线 managed；请配置 CDP 端点后重试。",
            )
        return "", fallback_reason, self._error_payload(
            error=f"cdp_unavailable:{fallback_reason}",
            scope="auto",
            requires_cdp=True,
            hint="CDP 暂不可用，请稍后重试。",
        )

    def _acquire_cdp_session(
        self,
        *,
        user_id: int,
        workspace: str,
        profile_id: str = "",
        action: str = "",
        allow_restart_confirmation: bool = False,
        confirmed: bool = False,
        next_args: dict[str, Any] | None = None,
    ) -> tuple[BrowserSession | None, dict[str, Any] | None]:
        try:
            session = self._get_session(user_id=user_id, workspace=workspace, mode="cdp", profile_id=profile_id)
            return session, None
        except Exception as exc:
            reason = str(exc)[:160]
            if allow_restart_confirmation and "cdp_requires_browser_restart" in reason:
                if confirmed:
                    restart_meta = self.force_restart_to_cdp(
                        timeout_seconds=self._recommended_restart_timeout_seconds(),
                        user_id=user_id,
                        workspace=workspace,
                        profile_id=profile_id,
                    )
                    if bool(restart_meta.get("ok")):
                        try:
                            session = self._get_session(
                                user_id=user_id,
                                workspace=workspace,
                                mode="cdp",
                                profile_id=profile_id,
                            )
                            return session, None
                        except Exception as retry_exc:
                            retry_reason = str(retry_exc)[:160]
                            return None, self._error_payload(
                                error=f"cdp_unavailable:{retry_reason}",
                                action=action,
                                scope="cdp",
                            )
                    fail_payload = self._error_payload(
                        error="browser_restart_failed_for_cdp",
                        action=action,
                        scope="cdp",
                    )
                    fail_payload["restart"] = {
                        "attempted": True,
                        "ok": False,
                        "error": str(restart_meta.get("error") or "")[:180],
                        "terminated_pids": list(restart_meta.get("terminated_pids") or []),
                        "killed_pids": list(restart_meta.get("killed_pids") or []),
                        "failed_pids": list(restart_meta.get("failed_pids") or []),
                        "remaining_pids": list(restart_meta.get("remaining_pids") or []),
                    }
                    return None, fail_payload
                confirm_args = dict(next_args or {})
                confirm_args["scope"] = "cdp"
                confirm_args["confirm"] = True
                return None, {
                    "ok": False,
                    "error": "browser_restart_required_for_cdp",
                    "requires_confirmation": True,
                    "confirm_kind": "restart_to_cdp",
                    "risk_level": "medium",
                    "action": action,
                    "user_prompt": "该任务较为复杂，需要重启浏览器后才能执行，是否确认？",
                    "next_call": {
                        "tool": "browser_use",
                        "action": action,
                        "args": confirm_args,
                    },
                }
            return None, self._error_payload(error=f"cdp_unavailable:{reason}", action=action)

    def state_get(
        self,
        *,
        user_id: int,
        workspace: str,
        profile_id: str = "",
        scope: str = "auto",
        include_dom: bool = True,
        include_a11y: bool = False,
        max_targets: int = 30,
        max_items: int = 20,
        pid: int = 0,
    ) -> dict[str, Any]:
        profile = self._ensure_profile(user_id=user_id, workspace=workspace, profile_id=profile_id)
        user_scope = self._normalize_scope(scope)
        target_limit = _clamp_int(max_targets, 30, low=1, high=60)
        proc_limit = _clamp_int(max_items, 20, low=0, high=200)
        sticky_scope = self._get_preferred_scope(user_id=int(user_id), workspace=workspace)
        if user_scope == "all":
            sessions = self.list_sessions(
                user_id=user_id,
                workspace=workspace,
                scope="all",
                max_items=proc_limit,
                pid=int(pid or 0),
            )
            active_state = self.state_get(
                user_id=user_id,
                workspace=workspace,
                profile_id=profile.profile_id,
                scope="auto",
                include_dom=include_dom,
                include_a11y=include_a11y,
                max_targets=target_limit,
                max_items=proc_limit,
                pid=int(pid or 0),
            )
            return {
                "ok": bool(active_state.get("ok", False)),
                "scope": "all",
                "active_state": active_state,
                "managed_sessions": list(sessions.get("managed_sessions") or []),
                "system_processes": list(sessions.get("system_processes") or []),
                "cdp_enabled": bool(sessions.get("cdp_enabled")),
                "cdp_endpoint": str(sessions.get("cdp_endpoint") or ""),
                "error": str(active_state.get("error") or "")[:180] if not bool(active_state.get("ok", False)) else "",
                "requires_confirmation": bool(active_state.get("requires_confirmation", False)),
                "confirm_kind": str(active_state.get("confirm_kind") or "")[:48],
                "user_prompt": str(active_state.get("user_prompt") or "")[:220],
                "next_call": active_state.get("next_call") if isinstance(active_state.get("next_call"), dict) else {},
                "requires_cdp": bool(active_state.get("requires_cdp", False)),
            }

        runtime_scope, fallback_reason, early_payload = self._resolve_state_runtime_scope(
            user_scope="cdp" if user_scope == "auto" and sticky_scope == "cdp" and self._cdp_enabled else user_scope,
            include_dom=bool(include_dom),
            include_a11y=bool(include_a11y),
            proc_limit=proc_limit,
            pid=int(pid or 0),
        )
        if isinstance(early_payload, dict):
            return early_payload

        if runtime_scope != "cdp":
            return self._error_payload(error=f"unsupported_scope:{runtime_scope or user_scope}", scope=runtime_scope or user_scope)

        session, session_error = self._acquire_cdp_session(
            user_id=user_id,
            workspace=workspace,
            profile_id=profile.profile_id,
            action="state_get",
            allow_restart_confirmation=False,
        )
        if session_error:
            fallback = str((session_error or {}).get("error") or "")[:160]
            normalized_fallback = fallback.split(":", 1)[1].strip() if fallback.startswith("cdp_unavailable:") else fallback
            if bool(include_dom) or bool(include_a11y):
                if (
                    normalized_fallback in {"cdp_requires_browser_restart", "cdp_launch_timeout", "browser_restart_failed_for_cdp"}
                    or "cdp_requires_browser_restart" in normalized_fallback
                ):
                    next_args: dict[str, Any] = {
                        "scope": "cdp",
                        "include_dom": bool(include_dom),
                        "include_a11y": bool(include_a11y),
                        "max_targets": int(target_limit),
                        "max_items": int(proc_limit),
                        "pid": int(pid or 0),
                    }
                    return {
                        "ok": False,
                        "error": "browser_restart_confirmation_required",
                        "requires_confirmation": True,
                        "confirm_kind": "restart_to_cdp",
                        "risk_level": "medium",
                        "action": "state_get",
                        "scope": user_scope,
                        "user_prompt": "读取页面内容需要切换到 CDP 并重启浏览器，是否确认？",
                        "hint": "确认后将自动重启浏览器并继续执行页面读取。",
                        "next_call": {
                            "tool": "browser_state_get",
                            "action": "state_get",
                            "args": next_args,
                        },
                    }
                return {
                    "ok": False,
                    "error": fallback if fallback.startswith("cdp_unavailable:") else f"cdp_unavailable:{fallback}",
                    "scope": "cdp",
                    "requires_cdp": True,
                    "hint": "当前无法建立 CDP 会话，暂不支持 DOM/A11y 读取。",
                }
            system_processes = self._list_system_browser_processes(
                max_items=proc_limit,
                pid=int(pid or 0),
                include_details=False,
            )
            if system_processes:
                return {
                    "ok": True,
                    "scope": "external",
                    "system_processes": system_processes,
                    "scope_fallback": fallback if fallback.startswith("cdp_unavailable:") else f"cdp_unavailable:{fallback}",
                    "scope_note": "CDP 暂不可用，已退回到系统浏览器进程级状态读取。",
                }
            return {
                "ok": False,
                "error": fallback if fallback.startswith("cdp_unavailable:") else f"cdp_unavailable:{fallback}",
                "scope": "cdp",
                "requires_cdp": True,
            }
        if session is None:
            return self._error_payload(error="cdp_unavailable:session_missing", scope="cdp", requires_cdp=True)

        with session.lock:
            session.touch()
            snap = self._snapshot_page(
                page=session.page,
                mode=str(getattr(session, "mode", runtime_scope) or runtime_scope),
                include_dom=bool(include_dom),
                include_a11y=bool(include_a11y),
                max_targets=target_limit,
            )
            payload: dict[str, Any] = {
                "ok": True,
                "scope": runtime_scope,
                "session_id": session.session_id,
                "profile_id": profile.profile_id,
                "profile": self._profile_payload(profile),
                **snap,
            }
            if fallback_reason:
                payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
            if runtime_scope == "cdp":
                self._set_preferred_scope(user_id=int(user_id), workspace=workspace, scope="cdp")
            return payload

    @staticmethod
    def _resolve_locator(*, page: Any, target: str, strategy: str, role: str = "") -> Any:
        text = str(target or "").strip()
        mode = str(strategy or "auto").strip().lower()
        if mode == "selector":
            return page.locator(text).first
        if mode == "text":
            return page.get_by_text(text, exact=False).first
        if mode == "role":
            role_name = str(role or "button").strip().lower() or "button"
            return page.get_by_role(role_name, name=text).first
        # auto
        if BrowserAutomationService._is_selector_like(text):
            return page.locator(text).first
        for role_name in ("button", "link", "textbox", "menuitem"):
            try:
                locator = page.get_by_role(role_name, name=text).first
                if locator.count() > 0:
                    return locator
            except Exception:
                continue
        return page.get_by_text(text, exact=False).first

    def use(
        self,
        *,
        user_id: int,
        workspace: str,
        action: str,
        args: dict[str, Any],
        profile_id: str = "",
        scope: str = "auto",
    ) -> dict[str, Any]:
        act = str(action or "").strip().lower()
        if act not in {"navigate", "click", "type", "scroll", "wait"}:
            return self._error_payload(error="unsupported_action", action=act)

        target = str(args.get("target") or args.get("selector") or args.get("text") or "").strip()
        value = str(args.get("value") or "").strip()
        url = str(args.get("url") or "").strip()
        profile = self._ensure_profile(user_id=user_id, workspace=workspace, profile_id=profile_id)
        user_scope = self._normalize_scope(scope)
        runtime_scope = user_scope
        prefer_existing_cdp = False
        sticky_scope = self._get_preferred_scope(user_id=int(user_id), workspace=workspace)

        if runtime_scope == "auto":
            if act == "navigate":
                prefer_existing_cdp = bool(self._cdp_enabled) and (
                    sticky_scope == "cdp"
                    or self._has_reusable_cdp_session(
                        user_id=int(user_id),
                        workspace=workspace,
                        profile_id=profile.profile_id,
                    )
                )
                runtime_scope = "cdp" if prefer_existing_cdp else "external"
            elif self._is_complex_auto_action(act):
                if not self._cdp_enabled:
                    return self._error_payload(
                        error="cdp_disabled",
                        action=act,
                        scope="auto",
                        requires_cdp=True,
                        hint="该操作需要受控浏览器（CDP），当前未启用。",
                    )
                if not self._cdp_endpoint:
                    return self._error_payload(
                        error="cdp_endpoint_unconfigured",
                        action=act,
                        scope="auto",
                        requires_cdp=True,
                        hint="该操作需要受控浏览器（CDP），但当前未配置 CDP 端点。",
                    )
                has_system_browser = self._has_system_browser_process()
                cdp_ready = bool(
                    self._cdp_endpoint
                    and self._probe_cdp_endpoint(self._cdp_endpoint, timeout_seconds=0.35)
                )
                if has_system_browser and (not cdp_ready) and not bool(args.get("confirm")):
                    next_args = dict(args or {})
                    next_args["scope"] = "cdp"
                    next_args["confirm"] = True
                    return {
                        "ok": False,
                        "error": "browser_restart_confirmation_required",
                        "requires_confirmation": True,
                        "confirm_kind": "restart_to_cdp",
                        "risk_level": "medium",
                        "action": act,
                        "user_prompt": "该任务较为复杂，需要重启浏览器后才能执行，是否确认？",
                        "hint": "请在下一次 browser_use 调用中设置 confirm=true 以继续。",
                        "next_call": {
                            "tool": "browser_use",
                            "action": act,
                            "args": next_args,
                        },
                    }
                runtime_scope = "cdp"
        elif runtime_scope == "external" and sticky_scope == "cdp" and self._cdp_enabled:
            runtime_scope = "cdp"
            prefer_existing_cdp = True

        if runtime_scope in {"system", "all"}:
            return self._error_payload(error="unsupported_scope_for_use", action=act, scope=runtime_scope)

        if runtime_scope == "cdp":
            if not self._cdp_enabled:
                return self._error_payload(
                    error="cdp_disabled",
                    action=act,
                    scope="cdp",
                    requires_cdp=True,
                    hint="当前未启用受控浏览器（CDP），无法执行该操作。",
                )
            if not self._cdp_endpoint:
                return self._error_payload(
                    error="cdp_endpoint_unconfigured",
                    action=act,
                    scope="cdp",
                    requires_cdp=True,
                    hint="当前未配置 CDP 端点，无法执行该操作。",
                )

        if runtime_scope == "external":
            if act != "navigate":
                if bool(args.get("confirm")):
                    if not self._cdp_enabled:
                        return self._error_payload(
                            error="cdp_disabled",
                            action=act,
                            scope="external",
                            requires_cdp=True,
                            hint="当前外部浏览器模式仅支持打开链接；该操作需要先启用 CDP。",
                        )
                    if not self._cdp_endpoint:
                        return self._error_payload(
                            error="cdp_endpoint_unconfigured",
                            action=act,
                            scope="external",
                            requires_cdp=True,
                            hint="当前外部浏览器模式仅支持打开链接；该操作需要先配置 CDP 端点。",
                        )
                    runtime_scope = "cdp"
                else:
                    if not self._cdp_enabled:
                        return self._error_payload(
                            error="cdp_disabled",
                            action=act,
                            scope="external",
                            requires_cdp=True,
                            hint="当前外部浏览器模式仅支持打开链接；该操作需要先启用 CDP。",
                        )
                    if not self._cdp_endpoint:
                        return self._error_payload(
                            error="cdp_endpoint_unconfigured",
                            action=act,
                            scope="external",
                            requires_cdp=True,
                            hint="当前外部浏览器模式仅支持打开链接；该操作需要先配置 CDP 端点。",
                        )
                    next_args = dict(args or {})
                    next_args["scope"] = "cdp"
                    next_args["confirm"] = True
                    return {
                        "ok": False,
                        "error": "external_scope_requires_cdp_for_dom",
                        "requires_confirmation": True,
                        "confirm_kind": "restart_to_cdp",
                        "risk_level": "medium",
                        "action": act,
                        "scope": "external",
                        "user_prompt": "当前外部浏览器模式仅支持打开链接。该任务需要切换到受控浏览器（CDP）继续执行，是否确认？",
                        "hint": "确认后将自动切换到 CDP 继续执行当前步骤。",
                        "next_call": {
                            "tool": "browser_use",
                            "action": act,
                            "args": next_args,
                        },
                    }
            else:
                if not re.match(r"^https?://", url, flags=re.I):
                    return self._error_payload(error="invalid_url", action=act, scope="external")
                opened = self._open_external_url(url)
                if not opened:
                    return self._error_payload(error="external_open_failed", action=act, scope="external")
                return {
                    "ok": True,
                    "action": act,
                    "scope": "external",
                    "effect_summary": f"opened_external:{url[:120]}",
                    "requires_confirmation": False,
                    "risk_level": "low",
                    "external_opened": True,
                    "before": {"url": "", "title": ""},
                    "after": {"url": url[:800], "title": ""},
                    "session_id": "",
                    "profile_id": profile.profile_id,
                    "profile": self._profile_payload(profile),
                }

        if (
            act == "navigate"
            and self._is_sensitive_auth_domain(url)
            and not bool(args.get("confirm"))
            and not prefer_existing_cdp
        ):
            next_args = dict(args or {})
            next_args["confirm"] = True
            login_state = self.mark_login_pending(
                user_id=user_id,
                workspace=workspace,
                domain=self._extract_hostname(url),
                next_call={"tool": "browser_use", "action": act, "args": next_args},
                profile_id=profile.profile_id,
                reason="auth_guard",
            )
            return {
                "ok": False,
                "error": "auth_permission_required",
                "requires_confirmation": True,
                "confirm_kind": "auth_guard",
                "risk_level": "auth_guard",
                "action": act,
                "domain": self._extract_hostname(url),
                "profile_id": profile.profile_id,
                "profile": self._profile_payload(profile),
                "login_request_id": str(login_state.get("request_id") or ""),
                "login_state": login_state,
                "fallback_scope": "external",
                "supported_scopes": ["auto", "cdp", "external"],
                "hint": (
                    "使用 confirm=true 可继续受控浏览器导航；"
                    "若需要继承用户登录态，可改用 scope=external。"
                ),
                "next_call": {
                    "tool": "browser_use",
                    "action": act,
                    "args": next_args,
                },
            }
        if self._is_high_risk(act, target=target, value=value, url=url) and not bool(args.get("confirm")):
            next_args = dict(args or {})
            next_args["confirm"] = True
            return {
                "ok": False,
                "error": "confirmation_required",
                "requires_confirmation": True,
                "confirm_kind": "high_risk_action",
                "risk_level": "high",
                "action": act,
                "next_call": {
                    "tool": "browser_use",
                    "action": act,
                    "args": next_args,
                },
            }

        timeout_ms = _clamp_int(args.get("timeout_ms"), self._default_timeout_ms, low=500, high=120000)
        strategy = str(args.get("strategy") or "auto").strip().lower()
        role = str(args.get("role") or "").strip().lower()
        fallback_reason = ""
        confirm_retry_args = {
            "url": url,
            "target": target,
            "value": value,
            "strategy": strategy,
            "role": role,
            "press_enter": bool(args.get("press_enter")),
            "direction": str(args.get("direction") or "").strip().lower(),
            "amount": _clamp_int(args.get("amount"), 720, low=-6000, high=6000),
            "wait_ms": _clamp_int(args.get("wait_ms"), 900, low=100, high=20000),
            "timeout_ms": _clamp_int(args.get("timeout_ms"), self._default_timeout_ms, low=500, high=120000),
            "scope": "cdp",
            "confirm": True,
        }
        if runtime_scope == "managed":
            return self._error_payload(
                error="managed_scope_soft_deleted",
                action=act,
                scope="managed",
                hint="managed 已软下线，请改用 scope=cdp 或 scope=external。",
            )

        if runtime_scope != "cdp":
            if self._cdp_endpoint:
                session, session_error = self._acquire_cdp_session(
                    user_id=user_id,
                    workspace=workspace,
                    profile_id=profile.profile_id,
                    action=act,
                    allow_restart_confirmation=True,
                    confirmed=bool(args.get("confirm")),
                    next_args=confirm_retry_args,
                )
                if session_error:
                    return session_error
                runtime_scope = "cdp"
            else:
                return self._error_payload(error="cdp_endpoint_unconfigured", action=act)
        else:
            session, session_error = self._acquire_cdp_session(
                user_id=user_id,
                workspace=workspace,
                profile_id=profile.profile_id,
                action=act,
                allow_restart_confirmation=True,
                confirmed=bool(args.get("confirm")),
                next_args=confirm_retry_args,
            )
            if session_error:
                return session_error
        if session is None:
            return self._error_payload(error="cdp_unavailable:session_missing", action=act)

        before = self.state_get(
            user_id=user_id,
            workspace=workspace,
            profile_id=profile.profile_id,
            scope=runtime_scope,
            include_dom=False,
            include_a11y=False,
            max_targets=1,
        )

        try:
            with session.lock:
                session.touch()
                page = session.page
                page.set_default_timeout(timeout_ms)

                if act == "navigate":
                    if not re.match(r"^https?://", url, flags=re.I):
                        return self._error_payload(error="invalid_url", action=act)
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    external_opened = False
                    if self._open_external_on_navigate and (not self._headless):
                        external_opened = self._open_external_url(url)
                    effect = f"navigated:{url[:120]}"
                elif act == "click":
                    if not target:
                        return self._error_payload(error="missing_target", action=act)
                    locator = self._resolve_locator(page=page, target=target, strategy=strategy, role=role)
                    locator.wait_for(state="visible", timeout=timeout_ms)
                    locator.click(timeout=timeout_ms)
                    effect = f"clicked:{target[:120]}"
                elif act == "type":
                    if not target:
                        return self._error_payload(error="missing_target", action=act)
                    locator = self._resolve_locator(page=page, target=target, strategy=strategy, role=role)
                    locator.wait_for(state="visible", timeout=timeout_ms)
                    locator.fill(value, timeout=timeout_ms)
                    if bool(args.get("press_enter")):
                        locator.press("Enter", timeout=timeout_ms)
                    effect = f"typed:{target[:120]}"
                elif act == "scroll":
                    amount = _clamp_int(args.get("amount"), 720, low=-6000, high=6000)
                    direction = str(args.get("direction") or "").strip().lower()
                    if direction == "up" and amount > 0:
                        amount = -amount
                    if direction == "down" and amount < 0:
                        amount = -amount
                    page.mouse.wheel(0, amount)
                    effect = f"scrolled:{amount}"
                else:  # wait
                    wait_ms = _clamp_int(args.get("wait_ms"), 900, low=100, high=20000)
                    page.wait_for_timeout(wait_ms)
                    effect = f"waited:{wait_ms}ms"
        except PlaywrightTimeoutError:
            return self._error_payload(error="timeout", action=act)
        except Exception as exc:
            return self._error_payload(error=str(exc)[:180], action=act)

        after = self.state_get(
            user_id=user_id,
            workspace=workspace,
            profile_id=profile.profile_id,
            scope=runtime_scope,
            include_dom=False,
            include_a11y=False,
            max_targets=1,
        )
        payload = {
            "ok": True,
            "action": act,
            "scope": runtime_scope,
            "effect_summary": effect,
            "requires_confirmation": False,
            "risk_level": "low",
            "external_opened": bool(external_opened) if act == "navigate" else False,
            "before": {"url": str(before.get("url") or ""), "title": str(before.get("title") or "")},
            "after": {"url": str(after.get("url") or ""), "title": str(after.get("title") or "")},
            "session_id": str(after.get("session_id") or ""),
            "profile_id": profile.profile_id,
            "profile": self._profile_payload(profile),
        }
        if fallback_reason:
            payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
        if runtime_scope == "cdp":
            self._set_preferred_scope(user_id=int(user_id), workspace=workspace, scope="cdp")
        elif runtime_scope == "external" and act == "navigate":
            self._set_preferred_scope(user_id=int(user_id), workspace=workspace, scope="external")
        return payload


browser_automation_service = BrowserAutomationService()