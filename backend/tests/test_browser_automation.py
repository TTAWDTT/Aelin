from __future__ import annotations

import threading
import time

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
    )
    assert out["ok"] is True
    assert out["external_opened"] is True
    assert page.goto_calls == ["https://github.com"]
    assert opened == ["https://github.com"]


def test_state_get_auto_fallbacks_from_cdp_to_managed(monkeypatch):
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
    assert out["scope"] == "managed"
    assert str(out.get("scope_fallback") or "").startswith("cdp_unavailable:")


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


def test_use_external_scope_blocks_dom_actions():
    service = BrowserAutomationService()
    out = service.use(
        user_id=1,
        workspace="default",
        action="click",
        args={"target": "Sign in", "confirm": True},
        scope="external",
    )
    assert out["ok"] is False
    assert out["error"] == "unsupported_action_in_external_scope"
