from __future__ import annotations

import threading

import app.services.aelin_loop_tools as aelin_loop_tools
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


class _FakeAttachmentService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search(self, db, *, user_id: int, workspace: str, query: str, attachment_ids: list[int], top_k: int, mode: str):
        self.calls.append(
            {
                "db": db,
                "user_id": user_id,
                "workspace": workspace,
                "query": query,
                "attachment_ids": list(attachment_ids),
                "top_k": top_k,
                "mode": mode,
            }
        )
        return {
            "ok": True,
            "attachment_ids": list(attachment_ids),
            "total": 1,
            "content": "[1] chunk text",
            "hits": [
                {
                    "chunk_id": 11,
                    "text": "chunk text",
                    "score": 1.0,
                    "citation": {"attachment_id": attachment_ids[0], "file_name": "demo.docx"},
                    "metadata": {"loc": {"page": 1}},
                }
            ],
        }


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


def test_browser_use_tool_passes_confirm_flag(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    captured: dict[str, object] = {}

    def _fake_use(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(aelin_tools.browser_automation_service, "use", _fake_use)

    result = hub.execute(
        "browser_use",
        {"action": "navigate", "scope": "managed", "url": "https://example.com", "confirm": False},
    )
    assert result["ok"] is True
    inner_args = captured.get("args")
    assert isinstance(inner_args, dict)
    assert inner_args.get("confirm") is False


def test_tool_definitions_include_external_browser_scope():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    defs = hub.tool_definitions()
    browser_use = next(
        item["function"] for item in defs if str(item.get("function", {}).get("name")) == "browser_use"
    )
    scope_enum = list(browser_use["parameters"]["properties"]["scope"]["enum"])
    assert "external" in scope_enum


def test_tool_definitions_include_browser_selector_and_text():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    defs = hub.tool_definitions()
    browser_use = next(
        item["function"] for item in defs if str(item.get("function", {}).get("name")) == "browser_use"
    )
    properties = browser_use["parameters"]["properties"]
    assert "selector" in properties
    assert "text" in properties


def test_browser_use_tool_offloads_when_running_event_loop(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    main_thread_id = threading.get_ident()
    captured: dict[str, object] = {}

    def _fake_use(**kwargs):
        captured["thread_id"] = threading.get_ident()
        captured["scope"] = kwargs.get("scope")
        return {"ok": True, "scope": kwargs.get("scope"), "action": kwargs.get("action")}

    monkeypatch.setattr(aelin_tools, "_has_running_event_loop", lambda: True)
    monkeypatch.setattr(aelin_tools.browser_automation_service, "use", _fake_use)

    result = hub.execute(
        "browser_use",
        {"action": "navigate", "scope": "managed", "url": "https://example.com", "confirm": True},
    )
    assert result["ok"] is True
    assert captured.get("scope") == "managed"
    assert int(captured.get("thread_id") or 0) != main_thread_id


def test_browser_use_tool_forwards_selector_and_text(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    captured: dict[str, object] = {}

    def _fake_use(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(aelin_tools.browser_automation_service, "use", _fake_use)

    result = hub.execute(
        "browser_use",
        {"action": "click", "selector": "[data-testid='tweet']", "text": "Pinned", "confirm": True},
    )
    assert result["ok"] is True
    inner_args = captured.get("args")
    assert isinstance(inner_args, dict)
    assert inner_args.get("selector") == "[data-testid='tweet']"
    assert inner_args.get("text") == "Pinned"


def test_browser_click_optimizer_allows_selector_without_target():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    rewritten, short_circuit = aelin_loop_tools._optimize_browser_tool_call(
        tool_hub=hub,
        tool_name="browser_use",
        args={"action": "click", "selector": "[data-testid='SideNav_NewTweet_Button']"},
    )

    assert rewritten["selector"] == "[data-testid='SideNav_NewTweet_Button']"
    assert short_circuit is None


def test_browser_record_result_does_not_mark_failed_navigate_as_observed():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    aelin_loop_tools._record_browser_tool_result(
        tool_hub=hub,
        tool_name="browser_use",
        args={"action": "navigate", "url": "https://x.com/following"},
        result={"ok": False, "error": "timeout"},
    )

    state = aelin_loop_tools._browser_loop_state(hub)
    assert state.last_observed_url == ""

    rewritten, short_circuit = aelin_loop_tools._optimize_browser_tool_call(
        tool_hub=hub,
        tool_name="browser_use",
        args={"action": "navigate", "url": "https://x.com/following"},
    )

    assert rewritten["url"] == "https://x.com/following"
    assert short_circuit is None


def test_compact_browser_state_result_keeps_snapshot_preview():
    compact = aelin_loop_tools._compact_tool_result_for_model(
        "browser_state_get",
        {
            "ok": True,
            "summary": "页面标题: Home / X；可操作元素: Following / Profile；加载状态: complete",
            "snapshot": {
                "url": "https://x.com/home",
                "title": "Home / X",
                "ready_state": "complete",
                "focus_targets": [
                    {"label": "Following", "tag": "a", "role": "link", "selector_hint": "a[href='/following']"},
                    {"label": "Profile", "tag": "a", "role": "link", "selector_hint": "a[href='/user']"},
                ],
            },
        },
    )

    snapshot = compact.get("snapshot") if isinstance(compact.get("snapshot"), dict) else {}
    assert snapshot.get("title") == "Home / X"
    focus_targets = snapshot.get("focus_targets") if isinstance(snapshot.get("focus_targets"), list) else []
    assert focus_targets[0]["tag"] == "a"


def test_attachment_search_uses_available_ids_fallback():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=7,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        tracking_service=_DummyTracking(),  # type: ignore[arg-type]
        file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=fake_attachment,  # type: ignore[arg-type]
        available_attachment_ids=[3, "2", 3, 0],  # type: ignore[list-item]
    )
    result = hub.execute("attachment_search", {"query": "总结附件"})
    assert result["ok"] is True
    assert result["attachment_ids"] == [2, 3]
    assert fake_attachment.calls[0]["attachment_ids"] == [2, 3]


def test_attachment_search_prefers_explicit_ids():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=7,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        tracking_service=_DummyTracking(),  # type: ignore[arg-type]
        file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=fake_attachment,  # type: ignore[arg-type]
        available_attachment_ids=[9, 10],
    )
    result = hub.execute(
        "attachment_search",
        {"query": "翻译", "attachment_ids": [5, "6", -1], "top_k": 6, "mode": "hybrid"},  # type: ignore[list-item]
    )
    assert result["ok"] is True
    assert result["attachment_ids"] == [5, 6]
    assert fake_attachment.calls[0]["attachment_ids"] == [5, 6]
    assert fake_attachment.calls[0]["top_k"] == 6
    assert fake_attachment.calls[0]["mode"] == "hybrid"
