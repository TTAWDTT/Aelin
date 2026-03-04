from __future__ import annotations

import json
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
    mode: str
    owner_thread_id: int
    playwright: Any
    browser: Any
    context: Any
    page: Any
    created_at: float
    last_used: float
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


class BrowserAutomationService:
    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = threading.RLock()
        self._creation_locks: dict[str, threading.Lock] = {}
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

    @staticmethod
    def _resolve_runtime_path(raw: str) -> Path:
        path = Path(str(raw or "").strip() or ".").expanduser()
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).resolve().parents[2]
        return (backend_dir / path).resolve()

    @staticmethod
    def _session_key(*, user_id: int, workspace: str, mode: str) -> str:
        safe_mode = str(mode or "managed").strip().lower() or "managed"
        return f"{safe_mode}::{int(user_id)}::{_normalize_workspace(workspace)}"

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

    def _create_managed_session(self, *, user_id: int, workspace: str) -> BrowserSession:
        if sync_playwright is None:
            raise RuntimeError("playwright_unavailable")

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
            mode="managed",
            owner_thread_id=threading.get_ident(),
            playwright=pw,
            browser=browser,
            context=context,
            page=page,
            created_at=now,
            last_used=now,
        )

    def _create_cdp_session(self, *, user_id: int, workspace: str, endpoint: str) -> BrowserSession:
        if sync_playwright is None:
            raise RuntimeError("playwright_unavailable")
        target = str(endpoint or "").strip()
        if not re.match(r"^https?://", target, flags=re.I):
            raise RuntimeError("cdp_endpoint_invalid")

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
            mode="cdp",
            owner_thread_id=threading.get_ident(),
            playwright=pw,
            browser=browser,
            context=context,
            page=page,
            created_at=now,
            last_used=now,
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

    def _probe_cdp_endpoint(self, endpoint: str, *, timeout_seconds: float = 0.8) -> bool:
        target = str(endpoint or "").strip().rstrip("/")
        if not target:
            return False
        url = f"{target}/json/version"
        try:
            with urllib.request.urlopen(url, timeout=max(0.2, float(timeout_seconds))) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
            if not isinstance(payload, dict):
                return False
            return bool(str(payload.get("webSocketDebuggerUrl") or "").strip())
        except (urllib.error.URLError, TimeoutError, ValueError):
            return False
        except Exception:
            return False

    def _resolve_cdp_browser_executable(self) -> str:
        configured = str(self._cdp_browser_path or "").strip()
        if configured:
            candidate = Path(configured).expanduser()
            if candidate.exists():
                return str(candidate)

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
                full = Path(base) / suffix
                candidates.append(str(full))

        seen: set[str] = set()
        for item in candidates:
            norm = str(item or "").strip()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            if Path(norm).exists():
                return norm
        return ""

    def _launch_cdp_browser(self, endpoint: str) -> None:
        exe = self._resolve_cdp_browser_executable()
        if not exe:
            raise RuntimeError("cdp_browser_not_found")
        port = self._parse_cdp_port(endpoint)
        if port <= 0:
            raise RuntimeError("cdp_endpoint_invalid")

        cmd = [
            exe,
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            "--new-window",
            "about:blank",
        ]
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            raise RuntimeError(f"cdp_launch_failed:{str(exc)[:120]}") from exc

    def _ensure_cdp_endpoint_ready(self) -> None:
        endpoint = str(self._cdp_endpoint or "").strip()
        if not endpoint:
            raise RuntimeError("cdp_endpoint_unconfigured")
        if self._probe_cdp_endpoint(endpoint):
            return
        if not self._cdp_auto_launch:
            raise RuntimeError("cdp_endpoint_unavailable")
        if self._has_system_browser_process():
            raise RuntimeError("cdp_requires_browser_restart")

        with self._cdp_bootstrap_lock:
            if self._probe_cdp_endpoint(endpoint):
                return
            self._launch_cdp_browser(endpoint)
            deadline = time.time() + max(2.0, float(self._cdp_launch_timeout_seconds or 10.0))
            while time.time() < deadline:
                if self._probe_cdp_endpoint(endpoint):
                    return
                time.sleep(0.2)
        raise RuntimeError("cdp_launch_timeout")

    def _resolve_mode(self, mode: str) -> str:
        raw = str(mode or "").strip().lower()
        if raw in {"managed", "cdp", "system", "all", "auto"}:
            return raw
        default = str(self._mode_default or "auto").strip().lower()
        return default if default in {"managed", "cdp", "auto"} else "auto"

    def _create_session_for_mode(self, *, user_id: int, workspace: str, mode: str) -> BrowserSession:
        if mode == "cdp":
            self._ensure_cdp_endpoint_ready()
            return self._create_cdp_session(
                user_id=user_id,
                workspace=workspace,
                endpoint=self._cdp_endpoint,
            )
        if mode == "managed":
            return self._create_managed_session(user_id=user_id, workspace=workspace)
        raise RuntimeError(f"unsupported_session_mode:{mode}")

    def _get_session(self, *, user_id: int, workspace: str, mode: str = "auto") -> BrowserSession:
        resolved_mode = self._resolve_mode(mode)
        if resolved_mode == "auto":
            if self._cdp_enabled and self._cdp_endpoint:
                try:
                    return self._get_session(user_id=user_id, workspace=workspace, mode="cdp")
                except Exception:
                    pass
            return self._get_session(user_id=user_id, workspace=workspace, mode="managed")
        if resolved_mode not in {"managed", "cdp"}:
            raise RuntimeError(f"unsupported_session_mode:{resolved_mode}")

        key = self._session_key(user_id=user_id, workspace=workspace, mode=resolved_mode)
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

    def _list_system_browser_processes(self, *, max_items: int, pid: int = 0) -> list[dict[str, Any]]:
        if psutil is None:
            return []
        rows: list[dict[str, Any]] = []
        attrs = ["pid", "name", "exe", "cmdline", "status", "create_time", "memory_info"]
        for proc in psutil.process_iter(attrs=attrs):
            try:
                info = proc.info if isinstance(getattr(proc, "info", None), dict) else {}
                proc_pid = int(info.get("pid") or 0)
                if pid > 0 and proc_pid != pid:
                    continue
                name = str(info.get("name") or "").strip()
                exe = str(info.get("exe") or "").strip()
                cmd = info.get("cmdline")
                cmdline = " ".join([str(part) for part in (cmd or []) if str(part or "").strip()]).strip()
                low_name = name.lower()
                low_exe = exe.lower()
                if low_name not in _BROWSER_FAMILY_NAMES and (not any(k in low_exe for k in ("chrome", "edge", "firefox", "opera", "brave"))):
                    continue
                mem_obj = info.get("memory_info")
                rss = int(getattr(mem_obj, "rss", 0) or 0)
                rows.append(
                    {
                        "pid": proc_pid,
                        "name": name[:80],
                        "browser_family": self._guess_browser_family(name, exe, cmdline),
                        "status": str(info.get("status") or "")[:32],
                        "memory_mb": round(rss / (1024 * 1024), 2) if rss > 0 else 0.0,
                        "started_at": float(info.get("create_time") or 0.0),
                        "exe": exe[:260],
                        "cmdline": cmdline[:600],
                    }
                )
            except Exception:
                continue
        rows.sort(key=lambda it: (float(it.get("memory_mb") or 0.0), int(it.get("pid") or 0)), reverse=True)
        return rows[:max(1, min(200, int(max_items or 20)))]

    def _has_system_browser_process(self, *, pid: int = 0) -> bool:
        return bool(self._list_system_browser_processes(max_items=1, pid=int(pid or 0)))

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
        limit = max(1, min(200, int(max_items or 20)))
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
                            "last_used": float(getattr(session, "last_used", 0.0) or 0.0),
                            "created_at": float(getattr(session, "created_at", 0.0) or 0.0),
                            "owner_thread_id": int(getattr(session, "owner_thread_id", 0) or 0),
                        }
                    )
            out["managed_sessions"] = sorted(
                list(out["managed_sessions"]),
                key=lambda it: float(it.get("last_used") or 0.0),
                reverse=True,
            )[:limit]

        if include_system:
            out["system_processes"] = self._list_system_browser_processes(max_items=limit, pid=int(pid or 0))
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

    def state_get(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str = "auto",
        include_dom: bool = True,
        include_a11y: bool = False,
        max_targets: int = 30,
        max_items: int = 20,
        pid: int = 0,
    ) -> dict[str, Any]:
        normalized_scope = self._normalize_scope(scope)
        target_limit = _clamp_int(max_targets, 30, low=1, high=60)
        proc_limit = _clamp_int(max_items, 20, low=1, high=200)
        if normalized_scope in {"system", "external"}:
            return {
                "ok": True,
                "scope": normalized_scope,
                "system_processes": self._list_system_browser_processes(max_items=proc_limit, pid=int(pid or 0)),
                "scope_note": (
                    "系统浏览器进程视图（不保证可获得每个标签页 URL）。"
                    if normalized_scope == "system"
                    else "external scope 仅能读取系统浏览器进程级状态，无法直接读取 DOM。"
                ),
            }
        if normalized_scope == "all":
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
                scope="auto",
                include_dom=include_dom,
                include_a11y=include_a11y,
                max_targets=target_limit,
                max_items=proc_limit,
                pid=int(pid or 0),
            )
            return {
                "ok": True,
                "scope": "all",
                "active_state": active_state,
                "managed_sessions": list(sessions.get("managed_sessions") or []),
                "system_processes": list(sessions.get("system_processes") or []),
                "cdp_enabled": bool(sessions.get("cdp_enabled")),
                "cdp_endpoint": str(sessions.get("cdp_endpoint") or ""),
            }

        selected_scope = normalized_scope
        fallback_reason = ""
        if selected_scope == "auto":
            if self._cdp_enabled and self._cdp_endpoint:
                selected_scope = "cdp"
            else:
                system_processes = self._list_system_browser_processes(max_items=proc_limit, pid=int(pid or 0))
                if system_processes:
                    return {
                        "ok": True,
                        "scope": "external",
                        "system_processes": system_processes,
                        "scope_note": "检测到用户浏览器正在运行；当前为进程级状态读取，若需 DOM 级读取请启用 CDP。",
                    }
                selected_scope = "managed"
        if selected_scope == "cdp":
            try:
                session = self._get_session(user_id=user_id, workspace=workspace, mode="cdp")
            except Exception as exc:
                fallback_reason = str(exc)[:160]
                session = self._get_session(user_id=user_id, workspace=workspace, mode="managed")
                selected_scope = "managed"
        else:
            session = self._get_session(user_id=user_id, workspace=workspace, mode="managed")

        with session.lock:
            session.touch()
            snap = self._snapshot_page(
                page=session.page,
                mode=str(getattr(session, "mode", selected_scope) or selected_scope),
                include_dom=bool(include_dom),
                include_a11y=bool(include_a11y),
                max_targets=target_limit,
            )
            payload: dict[str, Any] = {
                "ok": True,
                "scope": selected_scope,
                "session_id": session.session_id,
                **snap,
            }
            if fallback_reason:
                payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
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
        scope: str = "auto",
    ) -> dict[str, Any]:
        act = str(action or "").strip().lower()
        if act not in {"navigate", "click", "type", "scroll", "wait"}:
            return {"ok": False, "error": "unsupported_action", "action": act}

        target = str(args.get("target") or args.get("selector") or args.get("text") or "").strip()
        value = str(args.get("value") or "").strip()
        url = str(args.get("url") or "").strip()
        requested_scope = self._normalize_scope(scope)

        if requested_scope == "auto":
            if act == "navigate":
                requested_scope = "external"
            elif self._is_complex_auto_action(act):
                has_system_browser = self._has_system_browser_process()
                if has_system_browser and not bool(args.get("confirm")):
                    return {
                        "ok": False,
                        "error": "browser_restart_confirmation_required",
                        "requires_confirmation": True,
                        "risk_level": "medium",
                        "action": act,
                        "user_prompt": "该任务较为复杂，需要重启浏览器后才能执行，是否确认？",
                        "hint": "请在下一次 browser_use 调用中设置 confirm=true 以继续。",
                    }
                if has_system_browser:
                    requested_scope = "cdp"
                else:
                    requested_scope = "cdp"

        if requested_scope in {"system", "all"}:
            return {"ok": False, "error": "unsupported_scope_for_use", "action": act, "scope": requested_scope}
        if requested_scope == "external":
            if act != "navigate":
                return {
                    "ok": False,
                    "error": "unsupported_action_in_external_scope",
                    "action": act,
                    "scope": "external",
                    "supported_actions": ["navigate"],
                }
            if not re.match(r"^https?://", url, flags=re.I):
                return {"ok": False, "error": "invalid_url", "action": act, "scope": "external"}
            opened = self._open_external_url(url)
            if not opened:
                return {"ok": False, "error": "external_open_failed", "action": act, "scope": "external"}
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
            }

        if act == "navigate" and self._is_sensitive_auth_domain(url) and not bool(args.get("confirm")):
            return {
                "ok": False,
                "error": "auth_permission_required",
                "requires_confirmation": True,
                "risk_level": "auth_guard",
                "action": act,
                "domain": self._extract_hostname(url),
                "fallback_scope": "external",
                "supported_scopes": ["auto", "managed", "cdp", "external"],
                "hint": (
                    "使用 confirm=true 可继续受控浏览器导航；"
                    "若需要继承用户登录态，可改用 scope=external。"
                ),
            }
        if self._is_high_risk(act, target=target, value=value, url=url) and not bool(args.get("confirm")):
            return {
                "ok": False,
                "error": "confirmation_required",
                "requires_confirmation": True,
                "risk_level": "high",
                "action": act,
            }

        timeout_ms = _clamp_int(args.get("timeout_ms"), self._default_timeout_ms, low=500, high=120000)
        strategy = str(args.get("strategy") or "auto").strip().lower()
        role = str(args.get("role") or "").strip().lower()
        selected_scope = requested_scope if requested_scope != "auto" else "auto"
        fallback_reason = ""

        if selected_scope == "cdp":
            try:
                session = self._get_session(user_id=user_id, workspace=workspace, mode="cdp")
            except Exception as exc:
                reason = str(exc)[:160]
                if "cdp_requires_browser_restart" in reason:
                    return {
                        "ok": False,
                        "error": "browser_restart_required_for_cdp",
                        "requires_confirmation": True,
                        "risk_level": "medium",
                        "action": act,
                        "user_prompt": "该任务较为复杂，需要重启浏览器后才能执行，是否确认？",
                    }
                return {"ok": False, "error": f"cdp_unavailable:{reason}", "action": act}
        elif selected_scope == "managed":
            session = self._get_session(user_id=user_id, workspace=workspace, mode="managed")
        else:
            if self._cdp_enabled and self._cdp_endpoint:
                try:
                    session = self._get_session(user_id=user_id, workspace=workspace, mode="cdp")
                    selected_scope = "cdp"
                except Exception as exc:
                    fallback_reason = str(exc)[:160]
                    session = self._get_session(user_id=user_id, workspace=workspace, mode="managed")
                    selected_scope = "managed"
            else:
                session = self._get_session(user_id=user_id, workspace=workspace, mode="managed")
                selected_scope = "managed"

        before = self.state_get(
            user_id=user_id,
            workspace=workspace,
            scope=selected_scope,
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
                        return {"ok": False, "error": "invalid_url", "action": act}
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    external_opened = False
                    if self._open_external_on_navigate and (not self._headless):
                        external_opened = self._open_external_url(url)
                    effect = f"navigated:{url[:120]}"
                elif act == "click":
                    if not target:
                        return {"ok": False, "error": "missing_target", "action": act}
                    locator = self._resolve_locator(page=page, target=target, strategy=strategy, role=role)
                    locator.wait_for(state="visible", timeout=timeout_ms)
                    locator.click(timeout=timeout_ms)
                    effect = f"clicked:{target[:120]}"
                elif act == "type":
                    if not target:
                        return {"ok": False, "error": "missing_target", "action": act}
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
            return {"ok": False, "error": "timeout", "action": act}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:180], "action": act}

        after = self.state_get(
            user_id=user_id,
            workspace=workspace,
            scope=selected_scope,
            include_dom=False,
            include_a11y=False,
            max_targets=1,
        )
        payload = {
            "ok": True,
            "action": act,
            "scope": selected_scope,
            "effect_summary": effect,
            "requires_confirmation": False,
            "risk_level": "low",
            "external_opened": bool(external_opened) if act == "navigate" else False,
            "before": {"url": str(before.get("url") or ""), "title": str(before.get("title") or "")},
            "after": {"url": str(after.get("url") or ""), "title": str(after.get("title") or "")},
            "session_id": str(after.get("session_id") or ""),
        }
        if fallback_reason:
            payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
        return payload


browser_automation_service = BrowserAutomationService()
