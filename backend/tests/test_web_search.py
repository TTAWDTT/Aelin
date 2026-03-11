from __future__ import annotations

from datetime import datetime, timezone
import json

import app.routers.aelin as aelin_router
from app.services.web_search import WebSearchResult, WebSearchService


def test_build_web_query_pack_prioritizes_sports_and_time() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pack = aelin_router._build_web_query_pack(
        query="nba recent games",
        base_queries=["nba recent games"],
        intent_contract={
            "time_scope": "recent",
            "freshness_hours": 24,
            "sports_result_intent": True,
            "requires_citations": True,
        },
        memory_snapshot={"matched_items": []},
        limit=5,
    )
    assert isinstance(pack, list) and pack
    assert any(
        any(key in q.lower() for key in ("score", "box score", "result", "fixtures", "recap"))
        for q in pack
    )
    assert any(today in q or "latest" in q.lower() for q in pack)
    assert pack[0].lower() != "nba recent games"


def test_build_retry_web_queries_avoids_used_and_uses_intent() -> None:
    used = ["nba recent games", "nba recent games score"]
    retry = aelin_router._build_retry_web_queries(
        "nba recent games",
        used,
        intent_contract={
            "time_scope": "recent",
            "freshness_hours": 24,
            "sports_result_intent": True,
            "requires_citations": True,
        },
        memory_snapshot={"matched_items": []},
    )
    assert retry
    used_norm = {q.lower() for q in used}
    assert all(q.lower() not in used_norm for q in retry)


def test_extract_search_subject_reduces_question_noise() -> None:
    query = "NBA\u6700\u8fd1\u6253\u4e86\u4ec0\u4e48\u6bd4\u8d5b\uff1f"
    subject = aelin_router._extract_search_subject(query)
    assert "\u6700\u8fd1" not in subject
    assert "\u4ec0\u4e48" not in subject
    assert "\u6bd4\u8d5b" not in subject


def test_extract_search_subject_removes_trailing_have() -> None:
    query = "\u9a6c\u5fb7\u91cc\u7ade\u6280\u6709\u4ec0\u4e48\u6bd4\u8d5b"
    subject = aelin_router._extract_search_subject(query)
    assert subject
    assert subject.endswith("\u6709") is False


def test_decompose_web_context_boundaries_llm_returns_facets() -> None:
    class _FakeSvc:
        def is_configured(self) -> bool:
            return True

        def _chat(self, messages, max_tokens=420, stream=False):
            return json.dumps(
                {
                    "facets": [
                        {"scope": "latest score", "query": "nba latest score", "priority": 1},
                        {"scope": "box score", "query": "nba box score", "priority": 2},
                        {"scope": "official", "query": "nba official scoreboard", "priority": 3},
                    ],
                    "reason": "orthogonal facets",
                }
            )

    out = aelin_router._decompose_web_context_boundaries(
        query="nba recent games",
        web_boundaries=[{"kind": "web", "query": "nba recent games", "scope": "raw"}],
        intent_contract={
            "time_scope": "recent",
            "freshness_hours": 24,
            "sports_result_intent": True,
            "requires_citations": True,
        },
        memory_snapshot={"matched_items": []},
        service=_FakeSvc(),
        provider="openai",
    )
    assert out.get("source") == "llm"
    boundaries = out.get("boundaries") or []
    assert len(boundaries) >= 3
    assert all(str(it.get("kind") or "") == "web" for it in boundaries)
    assert any("box score" in str(it.get("query") or "").lower() for it in boundaries)


def test_decompose_web_context_boundaries_invalid_json_uses_fallback() -> None:
    class _BadSvc:
        def is_configured(self) -> bool:
            return True

        def _chat(self, messages, max_tokens=420, stream=False):
            return "not-json"

    out = aelin_router._decompose_web_context_boundaries(
        query="nba recent games",
        web_boundaries=[{"kind": "web", "query": "nba recent games", "scope": "raw"}],
        intent_contract={
            "time_scope": "recent",
            "freshness_hours": 24,
            "sports_result_intent": True,
            "requires_citations": True,
        },
        memory_snapshot={"matched_items": []},
        service=_BadSvc(),
        provider="openai",
    )
    assert out.get("source") == "fallback"
    boundaries = out.get("boundaries") or []
    assert boundaries
    assert all(str(it.get("kind") or "") == "web" for it in boundaries)


def test_decompose_web_context_boundaries_retry_can_recover() -> None:
    class _RetrySvc:
        def __init__(self) -> None:
            self.calls = 0

        def is_configured(self) -> bool:
            return True

        def _chat(self, messages, max_tokens=420, stream=False):
            self.calls += 1
            if self.calls == 1:
                return "not-json"
            return json.dumps(
                {
                    "facets": [
                        {"scope": "today result", "query": "nba today result", "priority": 1},
                        {"scope": "official", "query": "nba official scoreboard", "priority": 2},
                        {"scope": "recap", "query": "nba game recap", "priority": 3},
                    ],
                    "reason": "retry recovered",
                }
            )

    svc = _RetrySvc()
    out = aelin_router._decompose_web_context_boundaries(
        query="nba recent games",
        web_boundaries=[{"kind": "web", "query": "nba recent games", "scope": "raw"}],
        intent_contract={
            "time_scope": "recent",
            "freshness_hours": 24,
            "sports_result_intent": True,
            "requires_citations": True,
        },
        memory_snapshot={"matched_items": []},
        service=svc,
        provider="openai",
    )
    assert svc.calls >= 2
    assert out.get("source") == "llm"
    assert "retry=1" in str(out.get("reason") or "")


def test_web_search_fetch_prefers_reader_fallback_when_http_weak(monkeypatch) -> None:
    svc = WebSearchService(timeout_seconds=5)

    def _fake_http(url: str, *, max_chars: int):
        return "", "too short", {"blocked": False, "js_required": False}

    def _fake_reader(url: str, *, max_chars: int):
        return "Reader title", "reader text " * 40

    def _fake_browser(url: str, *, max_chars: int):
        return "", ""

    monkeypatch.setattr(svc, "_fetch_page_excerpt_http", _fake_http)
    monkeypatch.setattr(svc, "_fetch_page_excerpt_reader", _fake_reader)
    monkeypatch.setattr(svc, "_fetch_page_excerpt_browser", _fake_browser)

    title, excerpt, mode = svc._fetch_page_excerpt_best("https://example.com", max_chars=800)
    assert mode == "reader"
    assert title == "Reader title"
    assert len(excerpt) > 120


def test_web_search_search_and_fetch_attaches_provider_and_fetch_mode(monkeypatch) -> None:
    svc = WebSearchService(timeout_seconds=5)

    def _fake_search(query: str, *, max_results: int):
        return [
            WebSearchResult(title="A", url="https://example.com/a", snippet="alpha", provider="bing_html"),
            WebSearchResult(title="B", url="https://example.com/b", snippet="beta", provider="duckduckgo_lite"),
        ]

    def _fake_fetch(url: str, *, max_chars: int = 1800):
        if url.endswith("/a"):
            return "A title", "a excerpt " * 30, "http"
        return "B title", "b excerpt " * 30, "browser"

    monkeypatch.setattr(svc, "_search_with_ensemble", _fake_search)
    monkeypatch.setattr(svc, "_fetch_page_excerpt_best", _fake_fetch)

    rows = svc.search_and_fetch("demo", max_results=4, fetch_top_k=2)
    assert len(rows) == 2
    assert rows[0].fetch_mode == "http"
    assert rows[1].fetch_mode == "browser"
    assert rows[0].fetched_excerpt
    assert rows[1].fetched_excerpt
    assert rows[0].source == "web"
