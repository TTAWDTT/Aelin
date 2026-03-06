from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
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
from app.services.browser_login_checkpoint import browser_login_checkpoint_service
from app.services.browser_runtime_cdp import BrowserCdpRuntimeMixin
from app.services.browser_runtime_processes import BrowserProcessRuntimeMixin
from app.services.browser_runtime_sessions import BrowserSessionRuntimeMixin
from app.services.browser_runtime_state import BrowserStateRuntimeMixin

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
    BrowserCdpRuntimeMixin,
    BrowserSessionRuntimeMixin,
    BrowserProcessRuntimeMixin,
    BrowserStateRuntimeMixin,
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
        return browser_login_checkpoint_service.mark_login_pending(
            user_id=user_id,
            workspace=workspace,
            domain=domain,
            next_call=next_call,
            profile_id=profile.profile_id,
            reason=reason,
            resume_query=resume_query,
            resume_request=resume_request,
            continue_after_confirm=continue_after_confirm,
        )

    def get_login_state(
        self,
        *,
        user_id: int,
        workspace: str,
        request_id: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        return browser_login_checkpoint_service.get_login_state(
            user_id=user_id,
            workspace=workspace,
            request_id=request_id,
            profile_id=profile_id,
        )

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
        return browser_login_checkpoint_service.attach_login_resume_context(
            user_id=user_id,
            workspace=workspace,
            request_id=request_id,
            profile_id=profile_id,
            resume_query=resume_query,
            resume_request=resume_request,
            continue_after_confirm=continue_after_confirm,
        )

    def list_login_states(
        self,
        *,
        user_id: int,
        workspace: str = "",
        statuses: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return browser_login_checkpoint_service.list_login_states(
            user_id=user_id,
            workspace=workspace,
            statuses=statuses,
            limit=limit,
        )

    def cancel_login_pending(
        self,
        *,
        user_id: int,
        workspace: str,
        request_id: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        return browser_login_checkpoint_service.cancel_login_pending(
            user_id=user_id,
            workspace=workspace,
            request_id=request_id,
            profile_id=profile_id,
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
        return browser_login_checkpoint_service.resolve_login_pending(
            user_id=user_id,
            workspace=workspace,
            request_id=request_id,
            profile_id=profile_id,
            status=status,
        )

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
    def _is_complex_auto_action(action: str) -> bool:
        return str(action or "").strip().lower() in {"click", "type", "scroll", "wait"}

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

