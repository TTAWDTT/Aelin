from __future__ import annotations

import threading
import time
from pathlib import Path

from app.services.browser_automation import BrowserAutomationService


class _FakeSession:
    def __init__(self, *, owner_thread_id: int) -> None:
        self.session_id = "bs-test"
        self.owner_thread_id = int(owner_thread_id)
        self.mode = "managed"
        self.closed = False
        self.touched = 0

    def touch(self) -> None:
        self.touched += 1

    def close(self) -> None:
        self.closed = True


class _FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.timeout_ms = 0
        self.goto_calls: list[str] = []

    def title(self) -> str:
        return ""

    def evaluate(self, _script: str):
        return "complete"

    def set_default_timeout(self, timeout_ms: int) -> None:
        self.timeout_ms = int(timeout_ms)

    def goto(self, url: str, **_kwargs) -> None:
        self.url = str(url)
        self.goto_calls.append(str(url))

    def wait_for_timeout(self, _wait_ms: int) -> None:
        return None


class _FakeSessionWithPage(_FakeSession):
    def __init__(self, *, owner_thread_id: int, page: _FakePage) -> None:
        super().__init__(owner_thread_id=owner_thread_id)
        self.page = page
        self.lock = threading.RLock()


def test_get_session_reuses_same_thread_session(monkeypatch):
    service = BrowserAutomationService()
    service._sessions.clear()
    monkeypatch.setattr(service, "_cleanup_idle_sessions", lambda: None)

    key = service._session_key(user_id=1, workspace="default", mode="managed")
    thread_id = threading.get_ident()
    existing = _FakeSession(owner_thread_id=thread_id)
    service._sessions[key] = existing  # type: ignore[assignment]

    create_calls = {"count": 0}

    def _unexpected_create(**kwargs):
        create_calls["count"] += 1
        raise AssertionError("should not create session")

    monkeypatch.setattr(service, "_create_managed_session", _unexpected_create)

    out = service._get_session(user_id=1, workspace="default")
    assert out is existing
    assert existing.closed is False
    assert existing.touched == 1
    assert create_calls["count"] == 0


def test_get_session_recreates_when_thread_changed(monkeypatch):
    service = BrowserAutomationService()
    service._sessions.clear()
    monkeypatch.setattr(service, "_cleanup_idle_sessions", lambda: None)

    key = service._session_key(user_id=1, workspace="default", mode="managed")
    old = _FakeSession(owner_thread_id=111)
    new = _FakeSession(owner_thread_id=222)
    service._sessions[key] = old  # type: ignore[assignment]

    monkeypatch.setattr(threading, "get_ident", lambda: 222)

    create_calls = {"count": 0}

    def _fake_create(**kwargs):
        create_calls["count"] += 1
        return new

    monkeypatch.setattr(service, "_create_managed_session", _fake_create)

    out = service._get_session(user_id=1, workspace="default")
    assert out is new
    assert old.closed is True
    assert new.touched == 1
    assert create_calls["count"] == 1


def test_get_session_creates_outside_global_lock(monkeypatch):
    service = BrowserAutomationService()
    service._sessions.clear()
    monkeypatch.setattr(service, "_cleanup_idle_sessions", lambda: None)

    lock_available = {"value": False}

    def _fake_create(**kwargs):
        lock_available["value"] = bool(service._lock.acquire(blocking=False))
        if lock_available["value"]:
            service._lock.release()
        return _FakeSession(owner_thread_id=threading.get_ident())

    monkeypatch.setattr(service, "_create_managed_session", _fake_create)
    out = service._get_session(user_id=1, workspace="default", mode="managed")
    assert out is not None
    assert lock_available["value"] is True


def test_cleanup_idle_sessions_closes_outside_lock():
    service = BrowserAutomationService()
    key = service._session_key(user_id=1, workspace="default", mode="managed")

    class _ProbeSession(_FakeSession):
        def __init__(self, *, owner_thread_id: int) -> None:
            super().__init__(owner_thread_id=owner_thread_id)
            self.last_used = time.time() - 9_999
            self.close_outside_lock = False

        def close(self) -> None:
            acquired = service._lock.acquire(blocking=False)
            self.close_outside_lock = bool(acquired)
            if acquired:
                service._lock.release()
            super().close()

    probe = _ProbeSession(owner_thread_id=threading.get_ident())
    service._sessions[key] = probe  # type: ignore[assignment]
    service._cleanup_idle_sessions()
    assert probe.closed is True
    assert probe.close_outside_lock is True


def test_snapshot_page_marks_blank_scope():
    service = BrowserAutomationService()
    page = _FakePage()
    snap = service._snapshot_page(
        page=page,
        mode="managed",
        include_dom=False,
        include_a11y=False,
        max_targets=1,
    )
    assert snap["session_scope"] == "managed"
    assert snap["is_blank_page"] is True
    assert "agent" in str(snap.get("scope_note") or "").lower()


def test_use_navigate_can_open_external_browser(monkeypatch):
    service = BrowserAutomationService()
    page = _FakePage()
    session = _FakeSessionWithPage(owner_thread_id=threading.get_ident(), page=page)

    service._headless = False
    service._open_external_on_navigate = True

    monkeypatch.setattr(service, "_get_session", lambda **kwargs: session)

    states = iter(
        [
            {"ok": True, "url": "about:blank", "title": "", "session_id": "s1"},
            {"ok": True, "url": "https://github.com", "title": "GitHub", "session_id": "s1"},
        ]
    )
    monkeypatch.setattr(service, "state_get", lambda **kwargs: next(states))

    opened: list[str] = []
    monkeypatch.setattr(service, "_open_external_url", lambda url: opened.append(str(url)) or True)

    out = service.use(
        user_id=1,
        workspace="default",
        action="navigate",
        args={"url": "https://github.com", "confirm": True},
        scope="cdp",
    )
    assert out["ok"] is True
    assert out["external_opened"] is True
    assert page.goto_calls == ["https://github.com"]
    assert opened == ["https://github.com"]


def test_use_auto_navigate_prefers_external_scope(monkeypatch):
    service = BrowserAutomationService()
    opened: list[str] = []
    monkeypatch.setattr(service, "_open_external_url", lambda url: opened.append(str(url)) or True)

    out = service.use(
        user_id=1,
        workspace="default",
        action="navigate",
        args={"url": "https://example.com", "confirm": False},
        scope="auto",
    )
    assert out["ok"] is True
    assert out["scope"] == "external"
    assert out["external_opened"] is True
    assert opened == ["https://example.com"]


def test_state_get_auto_fallbacks_from_cdp_to_external(monkeypatch):
    service = BrowserAutomationService()
    page = _FakePage()
    managed = _FakeSessionWithPage(owner_thread_id=threading.get_ident(), page=page)
    managed.mode = "managed"
    service._cdp_enabled = True
    service._cdp_endpoint = "http://127.0.0.1:9222"

    def _fake_get_session(**kwargs):
        if kwargs.get("mode") == "cdp":
            raise RuntimeError("cdp_connect_failed")
        return managed

    monkeypatch.setattr(service, "_get_session", _fake_get_session)

    out = service.state_get(
        user_id=1,
        workspace="default",
        scope="auto",
        include_dom=False,
        include_a11y=False,
        max_targets=5,
    )
    assert out["ok"] is True
    assert out["scope"] == "external"
    assert str(out.get("scope_fallback") or "").startswith("cdp_unavailable:")


def test_state_get_auto_dom_requires_cdp_when_endpoint_unconfigured(monkeypatch):
    service = BrowserAutomationService()
    service._cdp_enabled = False
    service._cdp_endpoint = ""
    monkeypatch.setattr(
        service,
        "_list_system_browser_processes",
        lambda **kwargs: [{"pid": 1234, "name": "chrome.exe", "browser_family": "chrome"}],
    )

    out = service.state_get(
        user_id=1,
        workspace="default",
        scope="auto",
        include_dom=True,
        include_a11y=False,
        max_targets=10,
    )
    assert out["ok"] is False
    assert out["error"] == "cdp_endpoint_unconfigured"
    assert out.get("requires_cdp") is True


def test_state_get_external_with_dom_requires_cdp():
    service = BrowserAutomationService()
    out = service.state_get(
        user_id=1,
        workspace="default",
        scope="external",
        include_dom=True,
        include_a11y=False,
        max_targets=10,
    )
    assert out["ok"] is False
    assert out["error"] == "external_scope_requires_cdp_for_dom"
    assert out.get("requires_cdp") is True


def test_state_get_auto_dom_returns_confirmation_when_cdp_restart_needed(monkeypatch):
    service = BrowserAutomationService()
    service._cdp_endpoint = "http://127.0.0.1:9222"
    monkeypatch.setattr(service, "_probe_cdp_endpoint", lambda endpoint, **kwargs: False)
    monkeypatch.setattr(service, "_get_session", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("cdp_launch_timeout")))

    out = service.state_get(
        user_id=1,
        workspace="default",
        scope="auto",
        include_dom=True,
        include_a11y=False,
        max_targets=10,
    )
    assert out["ok"] is False
    assert out["error"] == "browser_restart_confirmation_required"
    assert out["requires_confirmation"] is True
    assert out["confirm_kind"] == "restart_to_cdp"
    next_call = out.get("next_call")
    assert isinstance(next_call, dict)
    assert str(next_call.get("tool") or "") == "browser_state_get"
    assert str(next_call.get("action") or "") == "state_get"
    next_args = next_call.get("args") if isinstance(next_call.get("args"), dict) else {}
    assert str(next_args.get("scope") or "") == "cdp"
    assert bool(next_args.get("include_dom")) is True
    assert bool(next_args.get("include_a11y")) is False


def test_state_get_all_propagates_confirmation_from_active_state(monkeypatch):
    service = BrowserAutomationService()
    monkeypatch.setattr(
        service,
        "list_sessions",
        lambda **kwargs: {
            "ok": True,
            "scope": "all",
            "managed_sessions": [],
            "system_processes": [],
            "cdp_enabled": True,
            "cdp_endpoint": "http://127.0.0.1:9222",
        },
    )
    original_state_get = service.state_get

    def _fake_state_get(**kwargs):
        if str(kwargs.get("scope") or "") == "auto":
            return {
                "ok": False,
                "error": "browser_restart_confirmation_required",
                "requires_confirmation": True,
                "confirm_kind": "restart_to_cdp",
                "user_prompt": "需要确认",
                "next_call": {"tool": "browser_state_get", "action": "state_get", "args": {"scope": "cdp"}},
            }
        return original_state_get(**kwargs)

    monkeypatch.setattr(service, "state_get", _fake_state_get)

    out = service.state_get(user_id=1, workspace="default", scope="all", include_dom=True)
    assert out["ok"] is False
    assert out["requires_confirmation"] is True
    assert out["confirm_kind"] == "restart_to_cdp"
    next_call = out.get("next_call")
    assert isinstance(next_call, dict)
    assert str(next_call.get("tool") or "") == "browser_state_get"


def test_use_auto_complex_requires_restart_confirmation_when_browser_running(monkeypatch):
    service = BrowserAutomationService()
    monkeypatch.setattr(service, "_probe_cdp_endpoint", lambda *args, **kwargs: False)
    monkeypatch.setattr(service, "_has_system_browser_process", lambda **kwargs: True)

    out = service.use(
        user_id=1,
        workspace="default",
        action="click",
        args={"target": "登录", "confirm": False},
        scope="auto",
    )
    assert out["ok"] is False
    assert out["error"] == "browser_restart_confirmation_required"
    assert out["requires_confirmation"] is True
    assert "该任务较为复杂" in str(out.get("user_prompt") or "")
    next_call = out.get("next_call")
    assert isinstance(next_call, dict)
    assert next_call.get("tool") == "browser_use"
    assert next_call.get("action") == "click"
    next_args = next_call.get("args")
    assert isinstance(next_args, dict)
    assert next_args.get("scope") == "cdp"
    assert next_args.get("confirm") is True
    assert next_args.get("target") == "登录"


def test_use_auto_complex_with_browser_running_restarts_to_cdp_after_confirm(monkeypatch):
    service = BrowserAutomationService()
    monkeypatch.setattr(service, "_probe_cdp_endpoint", lambda *args, **kwargs: False)
    monkeypatch.setattr(service, "_has_system_browser_process", lambda **kwargs: True)

    page = _FakePage()
    cdp_session = _FakeSessionWithPage(owner_thread_id=threading.get_ident(), page=page)
    cdp_session.mode = "cdp"
    calls = {"count": 0}

    def _fake_get_session(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("cdp_requires_browser_restart")
        return cdp_session

    monkeypatch.setattr(service, "_get_session", _fake_get_session)
    monkeypatch.setattr(service, "force_restart_to_cdp", lambda timeout_seconds=12.0: {"ok": True, "endpoint": "http://127.0.0.1:9222"})

    states = iter(
        [
            {"ok": True, "url": "about:blank", "title": "", "session_id": "s1"},
            {"ok": True, "url": "about:blank", "title": "", "session_id": "s1"},
        ]
    )
    monkeypatch.setattr(service, "state_get", lambda **kwargs: next(states))

    out = service.use(
        user_id=1,
        workspace="default",
        action="wait",
        args={"wait_ms": 100, "confirm": True},
        scope="auto",
    )
    assert out["ok"] is True
    assert out["scope"] == "cdp"


def test_use_auto_complex_with_browser_running_returns_restart_failed_when_confirmed(monkeypatch):
    service = BrowserAutomationService()
    monkeypatch.setattr(service, "_probe_cdp_endpoint", lambda *args, **kwargs: False)
    monkeypatch.setattr(service, "_has_system_browser_process", lambda **kwargs: True)
    monkeypatch.setattr(service, "_get_session", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("cdp_requires_browser_restart")))
    monkeypatch.setattr(
        service,
        "force_restart_to_cdp",
        lambda timeout_seconds=12.0: {"ok": False, "error": "cdp_conflict_process_still_running", "remaining_pids": [1, 2]},
    )

    out = service.use(
        user_id=1,
        workspace="default",
        action="click",
        args={"target": "登录", "confirm": True},
        scope="auto",
    )
    assert out["ok"] is False
    assert out["error"] == "browser_restart_failed_for_cdp"
    assert isinstance(out.get("restart"), dict)
    assert bool((out.get("restart") or {}).get("attempted")) is True


def test_use_auto_complex_without_browser_uses_cdp_when_enabled(monkeypatch):
    service = BrowserAutomationService()
    page = _FakePage()
    cdp_session = _FakeSessionWithPage(owner_thread_id=threading.get_ident(), page=page)
    cdp_session.mode = "cdp"
    monkeypatch.setattr(service, "_has_system_browser_process", lambda **kwargs: False)
    monkeypatch.setattr(service, "_get_session", lambda **kwargs: cdp_session)

    states = iter(
        [
            {"ok": True, "url": "about:blank", "title": "", "session_id": "s1"},
            {"ok": True, "url": "about:blank", "title": "", "session_id": "s1"},
        ]
    )
    monkeypatch.setattr(service, "state_get", lambda **kwargs: next(states))

    out = service.use(
        user_id=1,
        workspace="default",
        action="wait",
        args={"wait_ms": 200, "confirm": True},
        scope="auto",
    )
    assert out["ok"] is True
    assert out["scope"] == "cdp"


def test_use_auto_complex_skips_restart_confirmation_when_cdp_already_ready(monkeypatch):
    service = BrowserAutomationService()
    page = _FakePage()
    cdp_session = _FakeSessionWithPage(owner_thread_id=threading.get_ident(), page=page)
    cdp_session.mode = "cdp"
    monkeypatch.setattr(service, "_has_system_browser_process", lambda **kwargs: True)
    monkeypatch.setattr(service, "_probe_cdp_endpoint", lambda *args, **kwargs: True)
    monkeypatch.setattr(service, "_get_session", lambda **kwargs: cdp_session)

    states = iter(
        [
            {"ok": True, "url": "about:blank", "title": "", "session_id": "s1"},
            {"ok": True, "url": "about:blank", "title": "", "session_id": "s1"},
        ]
    )
    monkeypatch.setattr(service, "state_get", lambda **kwargs: next(states))

    out = service.use(
        user_id=1,
        workspace="default",
        action="wait",
        args={"wait_ms": 200, "confirm": False},
        scope="auto",
    )
    assert out["ok"] is True
    assert out["scope"] == "cdp"


def test_ensure_cdp_endpoint_ready_auto_launch_success(monkeypatch):
    service = BrowserAutomationService()
    service._cdp_endpoint = "http://127.0.0.1:9222"
    service._cdp_auto_launch = True
    service._cdp_launch_timeout_seconds = 0.8

    probe_calls = {"count": 0}

    def _fake_probe(endpoint: str, *, timeout_seconds: float = 0.8):
        probe_calls["count"] += 1
        return probe_calls["count"] >= 3

    launched: list[str] = []
    monkeypatch.setattr(service, "_probe_cdp_endpoint", _fake_probe)
    monkeypatch.setattr(service, "_launch_cdp_browser", lambda endpoint: launched.append(str(endpoint)))

    service._ensure_cdp_endpoint_ready()
    assert launched == ["http://127.0.0.1:9222"]
    assert probe_calls["count"] >= 3


def test_build_cdp_launch_command_uses_dedicated_profile_dir(tmp_path, monkeypatch):
    service = BrowserAutomationService()
    service._cdp_profile_dir = tmp_path / "cdp-profile"
    monkeypatch.setattr(service, "_resolve_cdp_browser_executable", lambda: str(tmp_path / "chrome.exe"))

    launch = service._build_cdp_launch_command("http://127.0.0.1:9222")

    assert str(launch.get("exe") or "").endswith("chrome.exe")
    assert Path(str(launch.get("user_data_dir") or "")).resolve() == (tmp_path / "cdp-profile").resolve()
    cmd = [str(item) for item in list(launch.get("cmd") or [])]
    assert any(item.startswith("--user-data-dir=") for item in cmd)
    assert not any("Google/Chrome/User Data" in item for item in cmd)


def test_resolve_cdp_browser_executable_prefers_cft_before_system(tmp_path, monkeypatch):
    service = BrowserAutomationService()
    cft = tmp_path / "chrome-for-testing" / "chrome.exe"
    chrome = tmp_path / "chrome.exe"
    cft.parent.mkdir(parents=True, exist_ok=True)
    cft.write_text("", encoding="utf-8")
    chrome.write_text("", encoding="utf-8")

    monkeypatch.setattr(service, "_list_cft_browser_candidates", lambda: [str(cft)])
    monkeypatch.setattr(service, "_list_system_browser_candidates", lambda: [str(chrome)])

    assert service._resolve_cdp_browser_executable() == str(cft)


def test_ensure_cdp_endpoint_ready_requires_restart_when_browser_running(monkeypatch):
    service = BrowserAutomationService()
    service._cdp_endpoint = "http://127.0.0.1:9222"
    service._cdp_auto_launch = True
    service._cdp_launch_timeout_seconds = 0.8
    monkeypatch.setattr(service, "_probe_cdp_endpoint", lambda endpoint, **kwargs: False)
    monkeypatch.setattr(service, "_launch_cdp_browser", lambda endpoint: None)
    monkeypatch.setattr(
        service,
        "_list_cdp_conflict_processes",
        lambda **kwargs: [{"pid": 222, "browser_family": "chrome", "name": "chrome.exe", "exe": "", "cmdline": ""}],
    )
    clock = {"t": 0.0}

    def _fake_time():
        clock["t"] += 1.1
        return clock["t"]

    monkeypatch.setattr("app.services.browser_automation.time.time", _fake_time)
    monkeypatch.setattr("app.services.browser_automation.time.sleep", lambda _seconds: None)

    try:
        service._ensure_cdp_endpoint_ready()
    except RuntimeError as exc:
        assert "cdp_requires_browser_restart" in str(exc)
    else:
        raise AssertionError("expected cdp_requires_browser_restart")


def test_ensure_cdp_endpoint_ready_without_auto_launch(monkeypatch):
    service = BrowserAutomationService()
    service._cdp_endpoint = "http://127.0.0.1:9222"
    service._cdp_auto_launch = False
    monkeypatch.setattr(service, "_probe_cdp_endpoint", lambda endpoint, **kwargs: False)

    try:
        service._ensure_cdp_endpoint_ready()
    except RuntimeError as exc:
        assert "cdp_endpoint_unavailable" in str(exc)
    else:
        raise AssertionError("expected cdp_endpoint_unavailable")


def test_use_navigate_requires_domain_confirmation():
    service = BrowserAutomationService()
    out = service.use(
        user_id=1,
        workspace="default",
        action="navigate",
        args={"url": "https://github.com", "confirm": False},
        scope="managed",
    )
    assert out["ok"] is False
    assert out["error"] == "auth_permission_required"
    assert out["fallback_scope"] == "external"
    next_call = out.get("next_call")
    assert isinstance(next_call, dict)
    assert next_call.get("action") == "navigate"
    next_args = next_call.get("args")
    assert isinstance(next_args, dict)
    assert next_args.get("confirm") is True


def test_use_sensitive_domain_auth_guard_takes_precedence_over_high_risk_keyword():
    service = BrowserAutomationService()
    out = service.use(
        user_id=1,
        workspace="default",
        action="navigate",
        args={"url": "https://github.com/settings/delete_token", "confirm": False},
        scope="managed",
    )
    assert out["ok"] is False
    assert out["error"] == "auth_permission_required"
    assert out["fallback_scope"] == "external"


def test_use_external_scope_navigate_opens_system_browser(monkeypatch):
    service = BrowserAutomationService()
    opened: list[str] = []
    monkeypatch.setattr(service, "_open_external_url", lambda url: opened.append(str(url)) or True)

    out = service.use(
        user_id=1,
        workspace="default",
        action="navigate",
        args={"url": "https://github.com", "confirm": True},
        scope="external",
    )
    assert out["ok"] is True
    assert out["scope"] == "external"
    assert out["external_opened"] is True
    assert opened == ["https://github.com"]


def test_use_external_scope_navigate_skips_auth_guard_without_confirm(monkeypatch):
    service = BrowserAutomationService()
    opened: list[str] = []
    monkeypatch.setattr(service, "_open_external_url", lambda url: opened.append(str(url)) or True)

    out = service.use(
        user_id=1,
        workspace="default",
        action="navigate",
        args={"url": "https://github.com", "confirm": False},
        scope="external",
    )
    assert out["ok"] is True
    assert out["scope"] == "external"
    assert opened == ["https://github.com"]


def test_use_auto_navigate_defaults_to_external_without_reusable_cdp(monkeypatch):
    service = BrowserAutomationService()
    opened: list[str] = []
    monkeypatch.setattr(service, "_open_external_url", lambda url: opened.append(str(url)) or True)

    out = service.use(
        user_id=1,
        workspace="default",
        action="navigate",
        args={"url": "https://x.com", "confirm": False},
        scope="auto",
    )
    assert out["ok"] is True
    assert out["scope"] == "external"
    assert opened == ["https://x.com"]


def test_use_auto_navigate_reuses_existing_cdp_session(monkeypatch):
    service = BrowserAutomationService()
    page = _FakePage()
    cdp_session = _FakeSessionWithPage(owner_thread_id=threading.get_ident(), page=page)
    cdp_session.mode = "cdp"
    key = service._session_key(user_id=1, workspace="default", mode="cdp")
    service._sessions[key] = cdp_session  # type: ignore[assignment]
    monkeypatch.setattr(service, "_open_external_url", lambda url: (_ for _ in ()).throw(AssertionError(f"unexpected external open: {url}")))
    monkeypatch.setattr(service, "_get_session", lambda **kwargs: cdp_session)

    states = iter(
        [
            {"ok": True, "url": "about:blank", "title": "", "session_id": "bs-test"},
            {"ok": True, "url": "https://x.com/following", "title": "Following", "session_id": "bs-test"},
        ]
    )
    monkeypatch.setattr(service, "state_get", lambda **kwargs: next(states))

    out = service.use(
        user_id=1,
        workspace="default",
        action="navigate",
        args={"url": "https://x.com/following", "confirm": False},
        scope="auto",
    )
    assert out["ok"] is True
    assert out["scope"] == "cdp"
    assert out["external_opened"] is False
    assert page.goto_calls == ["https://x.com/following"]


def test_use_external_scope_requests_confirmation_for_dom_actions():
    service = BrowserAutomationService()
    out = service.use(
        user_id=1,
        workspace="default",
        action="click",
        args={"target": "Sign in", "confirm": False},
        scope="external",
    )
    assert out["ok"] is False
    assert out["error"] == "external_scope_requires_cdp_for_dom"
    assert out["requires_confirmation"] is True
    assert out["confirm_kind"] == "restart_to_cdp"
    next_call = out.get("next_call")
    assert isinstance(next_call, dict)
    assert next_call.get("tool") == "browser_use"
    assert next_call.get("action") == "click"
    next_args = next_call.get("args")
    assert isinstance(next_args, dict)
    assert next_args.get("scope") == "cdp"
    assert next_args.get("confirm") is True


def test_use_external_scope_dom_action_with_confirm_switches_to_cdp(monkeypatch):
    service = BrowserAutomationService()
    page = _FakePage()
    cdp_session = _FakeSessionWithPage(owner_thread_id=threading.get_ident(), page=page)
    cdp_session.mode = "cdp"
    monkeypatch.setattr(service, "_get_session", lambda **kwargs: cdp_session)
    states = iter(
        [
            {"ok": True, "url": "about:blank", "title": "", "session_id": "s1"},
            {"ok": True, "url": "about:blank", "title": "", "session_id": "s1"},
        ]
    )
    monkeypatch.setattr(service, "state_get", lambda **kwargs: next(states))

    out = service.use(
        user_id=1,
        workspace="default",
        action="wait",
        args={"wait_ms": 200, "confirm": True},
        scope="external",
    )
    assert out["ok"] is True
    assert out["scope"] == "cdp"


def test_force_restart_to_cdp_launches_after_terminating_conflicts(monkeypatch):
    service = BrowserAutomationService()
    service._cdp_endpoint = "http://127.0.0.1:9222"
    service._cdp_auto_launch = True
    service._cdp_launch_timeout_seconds = 1.0

    state = {"probe_calls": 0, "conflict_calls": 0}

    def _fake_probe(endpoint: str, **kwargs):
        _ = endpoint, kwargs
        state["probe_calls"] += 1
        return state["probe_calls"] >= 3

    def _fake_conflicts(**kwargs):
        _ = kwargs
        state["conflict_calls"] += 1
        if state["conflict_calls"] == 1:
            return [{"pid": 111, "browser_family": "chrome", "name": "chrome.exe", "exe": "", "cmdline": ""}]
        return []

    launched: list[str] = []
    monkeypatch.setattr(service, "_probe_cdp_endpoint", _fake_probe)
    monkeypatch.setattr(service, "_list_cdp_conflict_processes", _fake_conflicts)
    monkeypatch.setattr(
        service,
        "_terminate_processes",
        lambda pids, wait_timeout_seconds=4.0: {
            "terminated_pids": list(pids),
            "killed_pids": [],
            "failed_pids": [],
        },
    )
    monkeypatch.setattr(service, "_launch_cdp_browser", lambda endpoint: launched.append(str(endpoint)))

    out = service.force_restart_to_cdp(timeout_seconds=2.0)
    assert out["ok"] is True
    assert launched == ["http://127.0.0.1:9222"]
    assert out.get("terminated_pids") == [111]


def test_force_restart_to_cdp_returns_error_when_conflicts_remain(monkeypatch):
    service = BrowserAutomationService()
    service._cdp_endpoint = "http://127.0.0.1:9222"
    monkeypatch.setattr(service, "_probe_cdp_endpoint", lambda endpoint, **kwargs: False)
    monkeypatch.setattr(
        service,
        "_list_cdp_conflict_processes",
        lambda **kwargs: [{"pid": 222, "browser_family": "chrome", "name": "chrome.exe", "exe": "", "cmdline": ""}],
    )
    monkeypatch.setattr(
        service,
        "_terminate_processes",
        lambda pids, wait_timeout_seconds=4.0: {
            "terminated_pids": list(pids),
            "killed_pids": [],
            "failed_pids": list(pids),
        },
    )

    out = service.force_restart_to_cdp(timeout_seconds=1.0)
    assert out["ok"] is False
    assert out["error"] == "cdp_conflict_process_still_running"


def test_force_restart_to_cdp_fallback_full_restart_can_recover(monkeypatch):
    service = BrowserAutomationService()
    service._cdp_endpoint = "http://127.0.0.1:9222"
    service._cdp_auto_launch = True
    service._cdp_launch_timeout_seconds = 0.8

    state = {"launch_calls": 0}

    def _fake_probe(endpoint: str, **kwargs):
        _ = endpoint, kwargs
        return state["launch_calls"] >= 2

    def _fake_launch(endpoint: str):
        _ = endpoint
        state["launch_calls"] += 1

    terminated_calls: list[list[int]] = []

    def _fake_terminate(pids, wait_timeout_seconds=4.0):
        _ = wait_timeout_seconds
        normalized = [int(pid) for pid in list(pids or []) if int(pid) > 0]
        terminated_calls.append(normalized)
        return {"terminated_pids": normalized, "killed_pids": [], "failed_pids": []}

    clock = {"t": 0.0}

    def _fake_time():
        clock["t"] += 1.0
        return clock["t"]

    monkeypatch.setattr(service, "_probe_cdp_endpoint", _fake_probe)
    monkeypatch.setattr(service, "_launch_cdp_browser", _fake_launch)
    monkeypatch.setattr(service, "_list_cdp_conflict_processes", lambda **kwargs: [])
    monkeypatch.setattr(service, "_list_chromium_family_pids", lambda max_items=200: [1234] if state["launch_calls"] == 1 else [])
    monkeypatch.setattr(service, "_terminate_processes", _fake_terminate)
    monkeypatch.setattr("app.services.browser_automation.time.time", _fake_time)
    monkeypatch.setattr("app.services.browser_automation.time.sleep", lambda _seconds: None)

    out = service.force_restart_to_cdp(timeout_seconds=1.0)
    assert out["ok"] is True
    assert out.get("fallback_full_restart") is True
    assert state["launch_calls"] == 2
    assert [1234] in terminated_calls
