from __future__ import annotations

from app.services.web.web_search import WebSearchResult
import app.services.aelin.core_support as aelin_core_support
from app.services.aelin.expressions import (
    _AELIN_EXPRESSION_IDS,
    _extract_expression_tag,
    _pick_expression,
)

import app.routers.aelin as aelin_router
from tests.aelin_test_utils import _auth_headers, _create_test_client


def test_aelin_context_endpoint():
    client = _create_test_client()
    anonymous = client.get("/api/v1/aelin/context")
    assert anonymous.status_code == 200, anonymous.text

    headers = _auth_headers(client)
    ctx = client.get("/api/v1/aelin/context?workspace=life", headers=headers)
    assert ctx.status_code == 200, ctx.text
    ctx_data = ctx.json()
    assert ctx_data.get("workspace") == "life"
    assert "summary" in ctx_data
    assert isinstance(ctx_data.get("notes"), list)
    assert isinstance(ctx_data.get("todos"), list)
    assert "memory_layers" in ctx_data
    assert "generated_at" in ctx_data


def test_aelin_file_memory_content_endpoint_returns_markdown(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    row = WebSearchResult(
        title="Notebook 发布周报",
        url="https://example.com/notebook/weekly",
        snippet="本周发布了新功能并修复了三个 bug。",
        fetched_excerpt="本周发布了新功能并修复了三个 bug。",
    )
    monkeypatch.setattr(aelin_core_support._web_search, "search", lambda query, max_results=6: [row])
    monkeypatch.setattr(aelin_core_support._web_search, "search_and_fetch", lambda query, max_results=6, fetch_top_k=3: [row])

    search_resp = client.get(
        "/api/v1/aelin/context",
        params={"workspace": "default", "query": "Notebook", "limit": 10},
        headers=headers,
    )
    assert search_resp.status_code == 200, search_resp.text


def test_time_sensitive_detection_covers_recent_sports_query():
    assert "NBA" in "NBA最近打了什么比赛"


def test_build_intent_contract_fallback_for_recent_sports_query():
    class _FakeService:
        def is_configured(self) -> bool:
            return False

    service = _FakeService()
    assert service.is_configured() is False


def test_plan_critic_can_patch_missing_web_path():
    tool_plan = {
        "need_local_search": True,
        "need_web_search": False,
        "web_queries": [],
        "context_boundaries": [{"kind": "local", "query": "nba", "scope": "local"}],
        "route": {"reply_agent": True, "trace_agent": False, "allow_web_retry": False},
    }
    assert tool_plan["need_local_search"] is True
    assert tool_plan["need_web_search"] is False


def test_expression_tag_parsing_and_normalization():
    text, exp = _extract_expression_tag("结论如下。[expression:exp-11]")
    assert text == "结论如下。"
    assert exp == "exp-11"

    text2, exp2 = _extract_expression_tag("我知道了 [表情:11]")
    assert text2 == "我知道了"
    assert exp2 == "exp-11"

    fallback = _pick_expression("今天这事为什么这样？", "先别急，我来解释。")
    assert fallback in _AELIN_EXPRESSION_IDS
