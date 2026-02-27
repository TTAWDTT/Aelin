from __future__ import annotations

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
