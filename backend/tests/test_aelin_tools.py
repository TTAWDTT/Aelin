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


class _FakeLLMCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        # Record the call and return a minimal JSON plan with a single open+text.
        self.calls.append(kwargs)
        content = '{"steps":[{"action":"open","url":"https://example.com"},{"action":"text"}]}'
        return type(
            "Resp",
            (object,),
            {
                "choices": [
                    type(
                        "Choice",
                        (object,),
                        {"message": type("Msg", (object,), {"content": content})()},
                    )()
                ]
            },
        )()


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


class _FakePinchTabClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def health(self) -> dict[str, object]:
        self.calls.append(("health", {}))
        return {"ok": True, "status": "healthy"}

    def launch_instance(self) -> dict[str, object]:
        self.calls.append(("launch_instance", {}))
        return {"ok": True, "instance_id": "inst-1"}

    def open_tab(self, *, instance_id: str, url: str) -> dict[str, object]:
        self.calls.append(("open_tab", {"instance_id": instance_id, "url": url}))
        return {"ok": True, "tab_id": "tab-1"}

    def snapshot(self, *, tab_id: str) -> dict[str, object]:
        self.calls.append(("snapshot", {"tab_id": tab_id}))
        return {"ok": True, "data": {"title": "Example"}}

    def text(self, *, tab_id: str, mode: str = "readable") -> dict[str, object]:
        self.calls.append(("text", {"tab_id": tab_id, "mode": mode}))
        return {"ok": True, "text": "page text"}

    def action(self, *, tab_id: str, kind: str, ref: str | None = None, **kwargs: object) -> dict[str, object]:
        payload: dict[str, object] = {"tab_id": tab_id, "kind": kind}
        if ref is not None:
            payload["ref"] = ref
        payload.update(kwargs)
        self.calls.append(("action", payload))
        return {"ok": True, "effect": "clicked"}


def _hub(fake_web: _FakeWebSearch, llm_service=None) -> AelinToolHub:
    return AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=1,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
        llm_service=llm_service,  # type: ignore[arg-type]
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


def test_attachment_search_uses_available_ids_fallback():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=7,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
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


def test_pinchtab_tool_calls_client_methods(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    fake_client = _FakePinchTabClient()
    monkeypatch.setattr(aelin_tools, "get_pinchtab_client", lambda: fake_client)

    # health
    result = hub.execute("pinchtab", {"action": "health"})
    assert result["ok"] is True
    assert any(call[0] == "health" for call in fake_client.calls)

    # launch + open_tab
    result = hub.execute("pinchtab", {"action": "launch_instance"})
    assert result["ok"] is True and result.get("instance_id") == "inst-1"

    result = hub.execute(
        "pinchtab",
        {"action": "open_tab", "instance_id": "inst-1", "url": "https://example.com"},
    )
    assert result["ok"] is True and result.get("tab_id") == "tab-1"

    # required parameter validation
    missing = hub.execute("pinchtab", {"action": "open_tab"})
    assert missing["ok"] is False and "missing instance_id or url" in str(missing.get("error") or "")

    # unsupported action
    unsupported = hub.execute("pinchtab", {"action": "unknown"})
    assert unsupported["ok"] is False


def test_pinchtab_agent_executes_plan_with_llm_and_client(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()

    hub = _hub(fake_web, llm_service=fake_service)  # type: ignore[arg-type]
    monkeypatch.setattr(aelin_tools, "get_pinchtab_client", lambda: fake_client)

    result = hub.execute("pinchtab_agent", {"goal": "打开 example.com 并读取文本"})
    assert result["ok"] is True
    assert result.get("instance_id") == "inst-1"
    assert result.get("tab_id") == "tab-1"
    assert "last_text" in result
    # Ensure the low-level client was actually used.
    called_ops = [name for name, _ in fake_client.calls]
    assert "launch_instance" in called_ops
    assert "open_tab" in called_ops
    assert "text" in called_ops
