from __future__ import annotations

import app.services.aelin_tools as aelin_tools
from app.services.aelin_tools import AelinToolHub
from app.services.web_search import WebSearchResult


class _DummyMemory:
    pass


class _DummyTracking:
    pass


class _DummyFileMemory:
    pass


class _FakeWebSearch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int]] = []

    def search(self, query: str, *, max_results: int = 6):
        self.calls.append(("search", query, int(max_results), 0))
        return [
            WebSearchResult(
                title="Search Title",
                url="https://example.com/a",
                snippet="snippet a",
                provider="duckduckgo_lite",
                fetch_mode="none",
                rank=1,
            )
        ]

    def search_and_fetch(self, query: str, *, max_results: int = 6, fetch_top_k: int = 3):
        self.calls.append(("search_and_fetch", query, int(max_results), int(fetch_top_k)))
        return [
            WebSearchResult(
                title="Fetched Title",
                url="https://example.com/b",
                snippet="snippet b",
                provider="bing_html",
                fetch_mode="http",
                rank=1,
                fetched_excerpt="fetched excerpt",
            )
        ]


def _hub(fake_web: _FakeWebSearch) -> AelinToolHub:
    return AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=1,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        tracking_service=_DummyTracking(),  # type: ignore[arg-type]
        file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
    )


def test_web_search_tool_search_and_fetch():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    result = hub.execute(
        "web_search",
        {
            "action": "search_and_fetch",
            "query": "DeepSeek 4.0",
            "max_results": 3,
            "fetch_top_k": 2,
        },
    )
    assert result["ok"] is True
    assert result["total"] == 1
    assert result["action"] == "search_and_fetch"
    assert result["providers"] == ["bing_html"]
    assert result["items"][0]["fetch_mode"] == "http"
    assert fake_web.calls[0] == ("search_and_fetch", "DeepSeek 4.0", 3, 2)


def test_web_search_tool_missing_query():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    result = hub.execute("web_search", {"action": "search", "query": ""})
    assert result["ok"] is False
    assert "missing query" in str(result.get("error") or "")
    assert fake_web.calls == []


def test_screen_get_tool_success(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(
        aelin_tools,
        "device_capture_screen",
        lambda **kwargs: {
            "data_url": "data:image/jpeg;base64,QUJDRA==",
            "name": "screen-demo.jpg",
            "width": 1280,
            "height": 720,
            "source_display": "1",
            "captured_at": "2026-03-04T01:00:00Z",
        },
    )

    result = hub.execute("screen_get", {"max_edge": 1024, "format": "jpeg"})
    assert result["ok"] is True
    assert str(result.get("data_url") or "").startswith("data:image/jpeg;base64,")
    assert result["width"] == 1280


def test_browser_state_get_tool_success(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(
        aelin_tools.browser_automation_service,
        "state_get",
        lambda **kwargs: {
            "ok": True,
            "session_id": "bs-test",
            "url": "https://example.com",
            "title": "Example",
            "ready_state": "complete",
            "interactive_targets": [{"tag": "button", "text": "Search"}],
            "a11y_nodes": [],
            "dom_digest": {"interactive_count": 1, "a11y_count": 0, "ready_state": "complete"},
        },
    )

    result = hub.execute("browser_state_get", {"include_dom": True, "max_targets": 10})
    assert result["ok"] is True
    assert result["url"] == "https://example.com"
    assert result["dom_digest"]["interactive_count"] == 1


def test_browser_session_list_tool_success(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(
        aelin_tools.browser_automation_service,
        "list_sessions",
        lambda **kwargs: {
            "ok": True,
            "scope": "all",
            "managed_sessions": [{"session_id": "bs1", "mode": "managed"}],
            "system_processes": [{"pid": 1234, "name": "chrome.exe"}],
            "cdp_enabled": True,
            "cdp_endpoint": "http://127.0.0.1:9222",
        },
    )

    result = hub.execute("browser_session_list", {"scope": "all", "max_items": 30})
    assert result["ok"] is True
    assert result["scope"] == "all"
    assert len(result["managed_sessions"]) == 1
    assert len(result["system_processes"]) == 1


def test_browser_use_tool_confirmation_required(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(
        aelin_tools.browser_automation_service,
        "use",
        lambda **kwargs: {
            "ok": False,
            "error": "confirmation_required",
            "requires_confirmation": True,
            "risk_level": "high",
            "action": "click",
        },
    )

    result = hub.execute(
        "browser_use",
        {"action": "click", "target": "Delete", "confirm": False},
    )
    assert result["ok"] is False
    assert result["error"] == "confirmation_required"
    assert result["requires_confirmation"] is True


def test_browser_use_tool_supports_external_scope(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    captured: dict[str, object] = {}

    def _fake_use(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "scope": kwargs.get("scope"), "action": kwargs.get("action")}

    monkeypatch.setattr(aelin_tools.browser_automation_service, "use", _fake_use)

    result = hub.execute(
        "browser_use",
        {"action": "navigate", "scope": "external", "url": "https://github.com", "confirm": True},
    )
    assert result["ok"] is True
    assert result["scope"] == "external"
    assert captured["scope"] == "external"


def test_tool_definitions_include_external_browser_scope():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    defs = hub.tool_definitions()
    browser_use = next(
        item["function"] for item in defs if str(item.get("function", {}).get("name")) == "browser_use"
    )
    scope_enum = list(browser_use["parameters"]["properties"]["scope"]["enum"])
    assert "external" in scope_enum
