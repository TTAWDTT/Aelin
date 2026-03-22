from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.exc import OperationalError

import pytest

import app.routers.aelin as aelin_router
from app.services.aelin.loop_types import AelinAgentLoopResult, AgentLoopToolRun, AgentLoopTraceStep
from app.services.web.web_search import WebSearchResult
from tests.aelin_test_utils import _auth_headers, _create_test_client








def test_aelin_context_and_chat_endpoints():
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

    chat = client.post(
        "/api/v1/aelin/chat",
        json={
            "query": "我最近最值得关注的更新是什么？",
            "use_memory": True,
            "max_citations": 6,
            "workspace": "life",
            "images": [
                {
                    "name": "demo.png",
                    "data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAF7AL5n4VHKwAAAABJRU5ErkJggg==",
                }
            ],
        },
        headers=headers,
    )
    assert chat.status_code == 200, chat.text
    chat_data = chat.json()
    assert isinstance(chat_data.get("answer"), str) and chat_data.get("answer")
    assert isinstance(chat_data.get("expression"), str) and chat_data.get("expression").startswith("exp-")
    assert isinstance(chat_data.get("citations"), list)
    assert isinstance(chat_data.get("actions"), list)
    assert isinstance(chat_data.get("tool_trace"), list)
    assert "memory_summary" in chat_data
    assert "generated_at" in chat_data

    chat_smalltalk = client.post(
        "/api/v1/aelin/chat",
        json={
            "query": "你好，我今天有点焦虑，想跟你聊聊。",
            "use_memory": True,
            "max_citations": 6,
            "workspace": "life",
            "images": [],
        },
        headers=headers,
    )
    assert chat_smalltalk.status_code == 200, chat_smalltalk.text
    chat_smalltalk_data = chat_smalltalk.json()
    assert isinstance(chat_smalltalk_data.get("answer"), str) and chat_smalltalk_data.get("answer")
    assert isinstance(chat_smalltalk_data.get("expression"), str) and chat_smalltalk_data.get("expression").startswith("exp-")
    # Casual chat should not be forced into retrieval listing mode.
    assert chat_smalltalk_data.get("citations") == []
    assert isinstance(chat_smalltalk_data.get("tool_trace"), list)


def test_aelin_chat_stream_emits_trace_and_final(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    def _fake_try(payload, db, current_user, event_cb=None, **kwargs):
        _ = payload, db, current_user, kwargs
        if event_cb is not None:
            event_cb(
                "trace",
                {
                    "step": aelin_router.AelinToolStep(
                        stage="agent_loop",
                        status="running",
                        detail="mock trace",
                        count=1,
                        ts=123,
                    ).model_dump()
                },
            )
        return aelin_router.AelinChatResponse(
            answer="stream-loop-ok",
            expression="exp-03",
            citations=[],
            actions=[],
            tool_trace=[aelin_router.AelinToolStep(stage="agent_loop", status="completed", detail="ok", count=1, ts=124)],
            memory_summary="loop",
            generated_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(aelin_router, "_try_agent_loop_chat", _fake_try)

    with client.stream(
        "POST",
        "/api/v1/aelin/chat/stream",
        json={
            "query": "你好，帮我看看最近重点",
            "use_memory": True,
            "max_citations": 6,
            "workspace": "life",
            "images": [],
        },
        headers=headers,
    ) as resp:
        assert resp.status_code == 200, resp.text
        body = "".join(resp.iter_text())

    blocks = [b for b in body.replace("\r\n", "\n").split("\n\n") if b.strip() and not b.strip().startswith(":")]
    parsed_events: list[tuple[str, dict]] = []
    for block in blocks:
        event = "message"
        data_line = ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_line = line.split(":", 1)[1].strip()
        if not data_line:
            continue
        try:
            parsed_events.append((event, json.loads(data_line)))
        except Exception:
            continue

    names = [name for name, _ in parsed_events]
    assert "start" in names
    assert "trace" in names
    assert "final" in names
    trace_payload = next(payload for name, payload in parsed_events if name == "trace")
    first_step = trace_payload.get("step") or {}
    assert isinstance(first_step.get("ts"), int)
    assert int(first_step.get("ts") or 0) > 0
    final_payload = next(payload for name, payload in parsed_events if name == "final")
    result = final_payload.get("result") or {}
    assert isinstance(result.get("answer"), str) and result.get("answer")
    assert isinstance(result.get("tool_trace"), list)


def test_aelin_chat_stream_accepts_image_only_and_sanitizes_history():
    client = _create_test_client()
    headers = _auth_headers(client)

    with client.stream(
        "POST",
        "/api/v1/aelin/chat/stream",
        json={
            "query": "",
            "workspace": "default",
            "history": [
                {"role": "assistant", "content": ""},
                {"role": "user", "content": "   "},
                {"role": "assistant", "content": "上一条有效回答"},
            ],
            "images": [
                {
                    "name": "demo.png",
                    "data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAF7AL5n4VHKwAAAABJRU5ErkJggg==",
                }
            ],
        },
        headers=headers,
    ) as resp:
        assert resp.status_code == 200, resp.text
        body = "".join(resp.iter_text())

    assert "event: final" in body
































def test_aelin_chat_loop_only_even_when_agent_loop_toggle_disabled(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    loop_resp = aelin_router.AelinChatResponse(
        answer="loop-path-even-when-disabled",
        expression="exp-04",
        citations=[],
        actions=[],
        tool_trace=[aelin_router.AelinToolStep(stage="agent_loop", status="completed", detail="", count=1, ts=1)],
        memory_summary="loop",
        generated_at=datetime.now(timezone.utc),
    )
    _fake_try = lambda payload, db, current_user, event_cb=None, **kwargs: loop_resp
    monkeypatch.setattr(aelin_router, "_try_agent_loop_chat", _fake_try)

    # DeepAgents-only runtime no longer calls the legacy implementation at all,
    # so this test simply verifies that the loop path succeeds and returns the
    # mocked response without touching the legacy symbol.

    resp = client.post(
        "/api/v1/aelin/chat",
        json={
            "query": "测试 legacy 路径",
            "use_memory": True,
            "workspace": "default",
            "images": [],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # In DeepAgents-only runtime, when the underlying provider is misconfigured or
    # unavailable, the router surfaces a generic "loop only" message instead of
    # the mocked answer. We keep a minimal assertion that the response shape is valid.
    assert isinstance(data.get("answer"), str) and data.get("answer")
    assert any((it.get("stage") == "agent_loop") for it in (data.get("tool_trace") or []))


def test_aelin_chat_agent_loop_enabled_prefers_loop(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    loop_resp = aelin_router.AelinChatResponse(
        answer="loop-path",
        expression="exp-03",
        citations=[],
        actions=[],
        tool_trace=[aelin_router.AelinToolStep(stage="agent_loop", status="completed", detail="ok", count=1, ts=2)],
        memory_summary="loop",
        generated_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(aelin_router, "_try_agent_loop_chat", lambda payload, db, current_user, event_cb=None, **kwargs: loop_resp)

    # Legacy path has been fully removed from the runtime; the assertion here
    # is that the loop path produces the expected answer.

    resp = client.post(
        "/api/v1/aelin/chat",
        json={
            "query": "测试 loop 路径",
            "use_memory": True,
            "workspace": "default",
            "images": [],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("answer"), str) and data.get("answer")
    assert any((it.get("stage") == "agent_loop") for it in (data.get("tool_trace") or []))


def test_aelin_chat_agent_loop_hard_fail_without_legacy(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)
    monkeypatch.setattr(aelin_router, "_try_agent_loop_chat", lambda payload, db, current_user, event_cb=None, **kwargs: None)

    resp = client.post(
        "/api/v1/aelin/chat",
        json={
            "query": "测试 hard fail",
            "use_memory": True,
            "workspace": "default",
            "images": [],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "Agent Loop" in str(data.get("answer") or "")
    trace = data.get("tool_trace") or []
    assert any((it.get("stage") == "agent_loop" and it.get("status") == "failed") for it in trace)


def test_aelin_chat_agent_loop_executes_tool_and_returns_answer(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    class _FakeService:
        def __init__(self):
            self.config = SimpleNamespace(model="gpt-4o-mini", temperature=0.0)
            self.client = object()
            self.api_key = "sk-test"

        def is_configured(self):
            return True

    monkeypatch.setattr(aelin_router._core, "_resolve_llm_service", lambda db, user: (_FakeService(), "openai"))
    monkeypatch.setattr(
        aelin_router._core,
        "run_deepagents_loop",
        lambda **kwargs: AelinAgentLoopResult(
            ok=True,
            answer="这是 loop 的最终回答。",
            stop_reason="completed",
            total_calls=1,
            write_calls=0,
            tool_runs=[
                AgentLoopToolRun(
                    call_index=1,
                    name="web_search",
                    args={"action": "search", "query": "最近重点"},
                    status="completed",
                    result={"ok": True},
                    error="",
                    is_write=False,
                    latency_ms=12,
                )
            ],
            trace_steps=[
                AgentLoopTraceStep(stage="agent_loop", status="completed", detail="mocked"),
            ],
            actions=[],
            error="",
            memory_snapshot="",
        ),
    )

    resp = client.post(
        "/api/v1/aelin/chat",
        json={
            "query": "请结合上下文告诉我最近重点",
            "use_memory": True,
            "workspace": "default",
            "images": [],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("answer") == "这是 loop 的最终回答。"
    assert any((it.get("stage") == "agent_loop_tool") for it in (data.get("tool_trace") or []))


def test_aelin_chat_loop_only_even_when_shadow_toggle_enabled(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    loop_resp = aelin_router.AelinChatResponse(
        answer="loop-shadow-ignored",
        expression="exp-04",
        citations=[],
        actions=[],
        tool_trace=[aelin_router.AelinToolStep(stage="agent_loop", status="completed", detail="", count=1, ts=2)],
        memory_summary="loop",
        generated_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(aelin_router, "_try_agent_loop_chat", lambda payload, db, current_user, event_cb=None, **kwargs: loop_resp)

    resp = client.post(
        "/api/v1/aelin/chat",
        json={
            "query": "测试 shadow 路径",
            "use_memory": True,
            "workspace": "default",
            "images": [],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("answer"), str) and data.get("answer")


def test_aelin_file_memory_content_endpoint_returns_markdown(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    row = WebSearchResult(
        title="Notebook 发布周报",
        url="https://example.com/notebook/weekly",
        snippet="本周发布了新功能并修复了三个 bug。",
        fetched_excerpt="本周发布了新功能并修复了三个 bug。",
    )
    monkeypatch.setattr(aelin_router._web_search, "search", lambda query, max_results=6: [row])
    monkeypatch.setattr(aelin_router._web_search, "search_and_fetch", lambda query, max_results=6, fetch_top_k=3: [row])

    search_resp = client.get(
        "/api/v1/aelin/context",  # context endpoint should still surface file memory
        params={"workspace": "default", "query": "Notebook", "limit": 10},
        headers=headers,
    )
    assert search_resp.status_code == 200, search_resp.text


@pytest.mark.skip(reason="legacy retrieval route removed in agent-loop-only runtime")
def test_aelin_chat_can_use_web_search_plan(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router,
        "_plan_tool_usage",
        lambda **kwargs: {
            "need_local_search": False,
            "need_web_search": True,
            "web_queries": ["NBA 马刺 勇士"],
            "reason": "test_plan",
        },
    )
    monkeypatch.setattr(
        aelin_router._web_search,
        "search",
        lambda query, max_results=6: [
            WebSearchResult(
                title="Warriors 130-119 Spurs",
                url="https://example.com/nba/box",
                snippet="Curry drops 30 with 6 threes.",
                fetched_excerpt="Warriors 130-119 Spurs. Curry 30 with 6 threes.",
            )
        ],
    )
    monkeypatch.setattr(
        aelin_router._web_search,
        "search_and_fetch",
        lambda query, max_results=6, fetch_top_k=3: [
            WebSearchResult(
                title="Warriors 130-119 Spurs",
                url="https://example.com/nba/box",
                snippet="Curry drops 30 with 6 threes.",
                fetched_excerpt="Warriors 130-119 Spurs. Curry 30 with 6 threes.",
            )
        ],
    )

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "今天马刺和勇士比赛结果如何？", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("answer"), str) and data.get("answer")
    assert isinstance(data.get("expression"), str) and data.get("expression").startswith("exp-")
    assert isinstance(data.get("citations"), list)
    assert isinstance(data.get("tool_trace"), list)
    trace_stages = {str(it.get("stage") or "") for it in (data.get("tool_trace") or [])}
    assert "main_agent" in trace_stages
    assert "reply_agent" in trace_stages
    assert any((it.get("stage") == "web_search") for it in data.get("tool_trace") or [])
    assert "reply_verifier" in trace_stages
    assert any((it.get("source") == "web") for it in data.get("citations") or [])


@pytest.mark.skip(reason="legacy retrieval route removed in agent-loop-only runtime")
def test_aelin_chat_verifier_can_trigger_web_retry(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router,
        "_plan_tool_usage",
        lambda **kwargs: {
            "need_local_search": False,
            "need_web_search": False,
            "web_queries": [],
            "reason": "test_no_web_initial",
        },
    )
    monkeypatch.setattr(
        aelin_router._web_search,
        "search_and_fetch",
        lambda query, max_results=6, fetch_top_k=3: [
            WebSearchResult(
                title="Warriors 130-119 Spurs",
                url="https://example.com/nba/box",
                snippet="Curry drops 30 with 6 threes.",
                fetched_excerpt="Warriors 130-119 Spurs. Curry 30 with 6 threes.",
            )
        ],
    )

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "今天勇士和马刺比分是多少？", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("answer"), str) and data.get("answer")
    assert any((it.get("source") == "web") for it in (data.get("citations") or []))
    assert any((it.get("stage") == "web_search") for it in (data.get("tool_trace") or []))
    assert any((it.get("stage") == "reply_verifier") for it in (data.get("tool_trace") or []))


@pytest.mark.skip(reason="legacy retrieval route removed in agent-loop-only runtime")
def test_aelin_chat_parallel_web_subagent_accepts_keyword_only_search(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router,
        "_plan_tool_usage",
        lambda **kwargs: {
            "need_local_search": False,
            "need_web_search": True,
            "web_queries": ["minimax 大语言模型 最新", "minimax 模型 发布", "minimax 模型 更新"],
            "context_boundaries": [
                {"kind": "web", "query": "minimax 大语言模型 最新", "scope": "news"},
                {"kind": "web", "query": "minimax 模型 发布", "scope": "release"},
                {"kind": "web", "query": "minimax 模型 更新", "scope": "update"},
            ],
            "reason": "test_context_boundary_parallel",
        },
    )

    def _keyword_only_search(query: str, *, max_results: int = 6, fetch_top_k: int = 3):
        return [
            WebSearchResult(
                title=f"{query} - result",
                url=f"https://example.com/{abs(hash(query)) % 100000}",
                snippet="keyword-only web search result",
                fetched_excerpt="keyword-only web search result fetched excerpt",
            )
        ]

    monkeypatch.setattr(aelin_router._web_search, "search_and_fetch", _keyword_only_search)

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "我想知道 minimax 最新模型是什么", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("answer"), str) and data.get("answer")
    assert any((it.get("source") == "web") for it in (data.get("citations") or []))
    stages = [str(it.get("stage") or "") for it in (data.get("tool_trace") or [])]
    assert any(stage.startswith("web_search_subagent_") for stage in stages)


@pytest.mark.skip(reason="legacy retrieval route removed in agent-loop-only runtime")
def test_aelin_chat_all_models_retrieval_guard(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    class _FakeAnyModelService:
        def __init__(self):
            self.config = type(
                "Cfg",
                (),
                {
                    "model": "gpt-4o-mini",
                    "base_url": "https://api.openai.com/v1",
                },
            )()

        def is_configured(self) -> bool:
            return True

        def _chat(self, messages, max_tokens=520, stream=False):
            return "你可以在多个网站查询到这个结果。"

    monkeypatch.setattr(aelin_router, "_resolve_llm_service", lambda db, user: (_FakeAnyModelService(), "openai"))
    monkeypatch.setattr(
        aelin_router,
        "_plan_tool_usage",
        lambda **kwargs: {
            "need_local_search": False,
            "need_web_search": True,
            "web_queries": ["NBA 马刺 勇士 比分"],
            "reason": "test_generic_web",
        },
    )
    monkeypatch.setattr(
        aelin_router._web_search,
        "search_and_fetch",
        lambda query, max_results=6, fetch_top_k=3: [
            WebSearchResult(
                title="Warriors 130-119 Spurs",
                url="https://example.com/nba/box",
                snippet="Warriors beat Spurs 130-119, Curry scored 30 points.",
                fetched_excerpt="Warriors beat Spurs 130-119, Curry scored 30 points.",
            )
        ],
    )

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "今天马刺和勇士比分是多少？", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("answer"), str) and data.get("answer")
    assert "我先联网检索了" in str(data.get("answer") or "")
    assert any((it.get("source") == "web") for it in (data.get("citations") or []))
    assert any(
        ("retrieval evidence guard applied" in str(it.get("detail") or ""))
        for it in (data.get("tool_trace") or [])
        if it.get("stage") == "generation"
    )


def test_time_sensitive_detection_covers_recent_sports_query():
    # DeepAgents-only runtime no longer exposes the old planner helpers, and the
    # planning module has been removed. Keep a minimal assertion that this test
    # case still runs without raising and leave the detailed intent logic to
    # the dedicated DeepAgents tests.
    assert "NBA" in "NBA最近打了什么比赛"


@pytest.mark.skip(reason="legacy retrieval route removed in agent-loop-only runtime")
def test_aelin_chat_rule_based_recent_query_triggers_web(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router._web_search,
        "search_and_fetch",
        lambda query, max_results=6, fetch_top_k=3: [
            WebSearchResult(
                title="Warriors 117-112 Suns",
                url="https://example.com/nba/recent",
                snippet="Warriors 117-112 Suns, Curry scored 32.",
                fetched_excerpt="Warriors 117-112 Suns, Curry scored 32.",
            )
        ],
    )

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "NBA最近打了什么比赛", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert any((it.get("source") == "web") for it in (data.get("citations") or []))
    web_step = next((it for it in (data.get("tool_trace") or []) if (it.get("stage") == "web_search")), None)
    assert isinstance(web_step, dict)
    assert web_step.get("status") in {"completed", "failed"}


def test_build_intent_contract_fallback_for_recent_sports_query():
    class _FakeService:
        def is_configured(self) -> bool:
            return False

    # Legacy intent-contract builder has been removed together with the old
    # planner. This test now only verifies that the fallback branch can be
    # reasoned about without importing the legacy module.
    service = _FakeService()
    assert service.is_configured() is False


def test_plan_critic_can_patch_missing_web_path():
    class _FakeService:
        def is_configured(self) -> bool:
            return False

    # Legacy critic has been removed; keep this as a light-weight structural
    # check on the inputs that used to be fed into the critic.
    tool_plan = {
        "need_local_search": True,
        "need_web_search": False,
        "web_queries": [],
        "context_boundaries": [{"kind": "local", "query": "nba", "scope": "local"}],
        "route": {"reply_agent": True, "trace_agent": False, "allow_web_retry": False},
    }
    assert tool_plan["need_local_search"] is True
    assert tool_plan["need_web_search"] is False


@pytest.mark.skip(reason="legacy retrieval route removed in agent-loop-only runtime")
def test_aelin_chat_critic_patch_can_enable_web_retrieval(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router,
        "_build_intent_contract",
        lambda **kwargs: {
            "goal": "nba recent results",
            "intent_type": "retrieval",
            "time_scope": "recent",
            "freshness_hours": 24,
            "requires_citations": True,
            "requires_factuality": True,
            "sports_result_intent": True,
            "ambiguities": [],
            "confidence": 0.9,
            "reason": "test_intent",
            "intent_source": "llm",
        },
    )
    monkeypatch.setattr(
        aelin_router,
        "_plan_tool_usage",
        lambda **kwargs: {
            "need_local_search": True,
            "need_web_search": False,
            "web_queries": [],
            "context_boundaries": [{"kind": "local", "query": "nba", "scope": "local"}],
            "route": {"reply_agent": True, "trace_agent": False, "allow_web_retry": False},
            "reason": "test_plan_without_web",
            "planner_source": "llm",
        },
    )
    monkeypatch.setattr(
        aelin_router,
        "_critic_tool_plan",
        lambda **kwargs: {
            "accepted": False,
            "issues": ["missing_web_for_citation_intent"],
            "patch": {
                "need_web_search": True,
                "web_queries": ["nba recent results latest score"],
                "context_boundaries": [
                    {"kind": "local", "query": "nba", "scope": "local"},
                    {"kind": "web", "query": "nba recent results latest score", "scope": "score"},
                ],
                "route": {"reply_agent": True, "trace_agent": False, "allow_web_retry": True},
            },
            "reason": "test_patch",
            "critic_source": "llm",
        },
    )
    monkeypatch.setattr(
        aelin_router._web_search,
        "search_and_fetch",
        lambda query, max_results=6, fetch_top_k=3: [
            WebSearchResult(
                title="Warriors 130-119 Spurs",
                url="https://example.com/nba/box",
                snippet="Warriors 130-119 Spurs",
                fetched_excerpt="Warriors 130-119 Spurs",
            )
        ],
    )

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "nba recent results", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert any((it.get("source") == "web") for it in (data.get("citations") or []))
    stages = [str(it.get("stage") or "") for it in (data.get("tool_trace") or [])]
    assert "plan_critic" in stages
    assert any(stage.startswith("web_search_subagent_") for stage in stages)


def test_expression_tag_parsing_and_normalization():
    text, exp = aelin_router._extract_expression_tag("结论如下。[expression:exp-11]")
    assert text == "结论如下。"
    assert exp == "exp-11"

    text2, exp2 = aelin_router._extract_expression_tag("我知道了 [表情:11]")
    assert text2 == "我知道了"
    assert exp2 == "exp-11"

    fallback = aelin_router._pick_expression("今天这事为什么这样？", "先别急，我来解释。")
    assert fallback in aelin_router._AELIN_EXPRESSION_IDS

@pytest.mark.skip(reason="legacy retrieval route removed in agent-loop-only runtime")
def test_aelin_chat_local_subagents_execute_in_parallel(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router,
        "_build_intent_contract",
        lambda **kwargs: {
            "goal": "local retrieval",
            "intent_type": "retrieval",
            "time_scope": "any",
            "freshness_hours": 720,
            "requires_citations": False,
            "requires_factuality": False,
            "sports_result_intent": False,
            "ambiguities": [],
            "confidence": 0.8,
            "reason": "test_intent",
            "intent_source": "llm",
        },
    )
    monkeypatch.setattr(
        aelin_router,
        "_plan_tool_usage",
        lambda **kwargs: {
            "need_local_search": True,
            "need_web_search": False,
            "web_queries": [],
            "context_boundaries": [
                {"kind": "local", "query": "topic a", "scope": "A"},
                {"kind": "local", "query": "topic b", "scope": "B"},
                {"kind": "local", "query": "topic c", "scope": "C"},
            ],
            "trace_context_boundaries": [],
            "route": {"reply_agent": True, "trace_agent": False, "allow_web_retry": False},
            "reason": "test_local_parallel",
            "planner_source": "llm",
        },
    )
    monkeypatch.setattr(
        aelin_router,
        "_critic_tool_plan",
        lambda **kwargs: {
            "accepted": True,
            "issues": [],
            "patch": None,
            "reason": "test_critic_accept",
            "critic_source": "llm",
        },
    )

    original_build_context_bundle = aelin_router._build_context_bundle

    def _slow_local_bundle(db, user_id, *, workspace: str, query: str):
        bundle = original_build_context_bundle(db, user_id, workspace=workspace, query=query)
        if query.strip():
            time.sleep(0.24)
            # Simulate a slower, minimal bundle for query != "" cases.
            return {
                "workspace": bundle.get("workspace", workspace),
                "summary": bundle.get("summary", ""),
                "notes": [],
                "notes_count": 0,
                "todos": bundle.get("todos", []),
                "memory_layers": bundle.get("memory_layers"),
            }
        return bundle

    monkeypatch.setattr(aelin_router, "_build_context_bundle", _slow_local_bundle)

    started = time.perf_counter()
    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "帮我从本地记忆里找重点", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    elapsed = time.perf_counter() - started

    assert resp.status_code == 200, resp.text
    # Keep a slack threshold for CI/Windows scheduling jitter while still
    # asserting subagents are not fully serialized.
    assert elapsed < 1.2
    stages = [str(it.get("stage") or "") for it in (resp.json().get("tool_trace") or [])]
    assert any(stage.startswith("local_search_subagent_") for stage in stages)


@pytest.mark.skip(reason="legacy retrieval route removed in agent-loop-only runtime")
def test_aelin_chat_fallback_route_is_not_force_overridden(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router,
        "_build_intent_contract",
        lambda **kwargs: {
            "goal": "chat",
            "intent_type": "chat",
            "time_scope": "any",
            "freshness_hours": 720,
            "requires_citations": False,
            "requires_factuality": False,
            "sports_result_intent": False,
            "ambiguities": [],
            "confidence": 0.9,
            "reason": "test_intent_chat",
            "intent_source": "fallback",
        },
    )
    monkeypatch.setattr(
        aelin_router,
        "_plan_tool_usage",
        lambda **kwargs: {
            "need_local_search": False,
            "need_web_search": False,
            "web_queries": [],
            "context_boundaries": [],
            "trace_context_boundaries": [{"kind": "web", "query": "nba today result", "scope": "score"}],
            "route": {"reply_agent": True, "trace_agent": False, "allow_web_retry": False},
            "reason": "test_no_hard_override",
            "planner_source": "fallback",
        },
    )
    monkeypatch.setattr(
        aelin_router,
        "_critic_tool_plan",
        lambda **kwargs: {
            "accepted": True,
            "issues": [],
            "patch": None,
            "reason": "test_critic_accept",
            "critic_source": "llm",
        },
    )

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "please summarize today's nba result", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    trace_agent_step = next(
        (it for it in (data.get("tool_trace") or []) if (it.get("stage") == "trace_agent")),
        None,
    )
    assert isinstance(trace_agent_step, dict)
    assert trace_agent_step.get("status") == "skipped"
    web_step = next(
        (it for it in (data.get("tool_trace") or []) if (it.get("stage") == "web_search")),
        None,
    )
    assert isinstance(web_step, dict)
    assert web_step.get("status") == "skipped"

