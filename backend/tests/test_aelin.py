from __future__ import annotations

import json
import tempfile
import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.routers.aelin as aelin_router
import app.services.device_center as device_center
from app.db import init_engine
from app.main import create_app
from app.models import Base
from app.services.web_search import WebSearchResult
from app.settings import settings


def _create_test_client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)

    init_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    import app.db as db_module

    db_module._engine = engine  # type: ignore[attr-defined]
    db_module._SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)  # type: ignore[attr-defined]

    tmp_media = tempfile.TemporaryDirectory()
    settings.media_dir = tmp_media.name
    app = create_app()
    client = TestClient(app)
    client._tmp_media = tmp_media  # type: ignore[attr-defined]
    return client


def _auth_headers(client: TestClient) -> dict[str, str]:
    reg = client.post("/api/v1/register", json={"email": "aelin@example.com", "password": "password123"})
    assert reg.status_code == 200, reg.text
    login = client.post(
        "/api/v1/token",
        data={"username": "aelin@example.com", "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _sync_and_wait(client: TestClient, headers: dict[str, str], account_id: int) -> None:
    started = client.post(f"/api/v1/accounts/{account_id}/sync", headers=headers)
    assert started.status_code in {200, 202}, started.text
    payload = started.json()
    if payload.get("status") == "succeeded":
        return
    job_id = payload.get("job_id")
    assert isinstance(job_id, str) and job_id
    for _ in range(200):
        resp = client.get(f"/api/v1/accounts/sync-jobs/{job_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        job = resp.json()
        if job.get("status") == "succeeded":
            return
        if job.get("status") == "failed":
            raise AssertionError(f"sync failed: {job.get('error')}")
        time.sleep(0.05)
    raise AssertionError("sync timed out")


def test_aelin_context_and_chat_endpoints():
    client = _create_test_client()
    anonymous = client.get("/api/v1/aelin/context")
    assert anonymous.status_code == 200, anonymous.text

    headers = _auth_headers(client)
    acct = client.post(
        "/api/v1/accounts",
        json={"provider": "mock", "identifier": "demo", "access_token": "x"},
        headers=headers,
    )
    assert acct.status_code == 200, acct.text
    _sync_and_wait(client, headers, int(acct.json()["id"]))

    ctx = client.get("/api/v1/aelin/context?workspace=life", headers=headers)
    assert ctx.status_code == 200, ctx.text
    ctx_data = ctx.json()
    assert ctx_data.get("workspace") == "life"
    assert "summary" in ctx_data
    assert isinstance(ctx_data.get("focus_items"), list)
    assert isinstance(ctx_data.get("notes"), list)
    assert isinstance(ctx_data.get("todos"), list)
    assert isinstance(ctx_data.get("pin_recommendations"), list)
    assert isinstance(ctx_data.get("layout_cards"), list)
    assert isinstance(ctx_data.get("daily_brief"), dict)
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


def test_aelin_chat_stream_emits_trace_and_final():
    client = _create_test_client()
    headers = _auth_headers(client)

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


def test_aelin_track_confirm_endpoint(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    missing = client.post(
        "/api/v1/aelin/track/confirm",
        json={"target": "NBA", "source": "x", "query": "跟踪 NBA 动态"},
        headers=headers,
    )
    assert missing.status_code == 200, missing.text
    missing_data = missing.json()
    assert missing_data.get("status") in {"sync_started", "needs_config"}
    assert missing_data.get("provider") == "x"
    assert any((it.get("kind") in {"open_settings", "open_desk"}) for it in (missing_data.get("actions") or []))

    monkeypatch.setattr(
        aelin_router._web_search,
        "search",
        lambda query, max_results=6: [
            WebSearchResult(
                title="Warriors beat Spurs 130-119",
                url="https://example.com/nba/game",
                snippet="Curry scored 30 with 6 threes.",
                fetched_excerpt="Warriors beat Spurs 130-119. Curry scored 30 with 6 threes.",
            )
        ],
    )
    monkeypatch.setattr(
        aelin_router._web_search,
        "search_and_fetch",
        lambda query, max_results=6, fetch_top_k=3: [
            WebSearchResult(
                title="Warriors beat Spurs 130-119",
                url="https://example.com/nba/game",
                snippet="Curry scored 30 with 6 threes.",
                fetched_excerpt="Warriors beat Spurs 130-119. Curry scored 30 with 6 threes.",
            )
        ],
    )
    ok = client.post(
        "/api/v1/aelin/track/confirm",
        json={"target": "NBA 比赛", "source": "web", "query": "NBA 马刺 勇士"},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    ok_data = ok.json()
    assert ok_data.get("status") == "tracking_enabled"
    assert ok_data.get("provider") == "web"
    contacts = client.get("/api/v1/contacts?q=Aelin%20Tracking&limit=12", headers=headers)
    assert contacts.status_code == 200, contacts.text
    assert any("Aelin Tracking" in str(row.get("display_name", "")) for row in contacts.json())

    tracking_list = client.get("/api/v1/aelin/tracking?limit=20", headers=headers)
    assert tracking_list.status_code == 200, tracking_list.text
    tracking_data = tracking_list.json()
    assert isinstance(tracking_data.get("items"), list)
    assert tracking_data.get("total", 0) >= 1
    assert any((row.get("target") == "NBA 比赛") for row in (tracking_data.get("items") or []))


def test_aelin_tracking_batch_ack_and_single_ack_compat(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    def _set_web_rows(url: str, title: str, snippet: str):
        row = WebSearchResult(
            title=title,
            url=url,
            snippet=snippet,
            fetched_excerpt=snippet,
        )
        monkeypatch.setattr(aelin_router._web_search, "search", lambda query, max_results=6: [row])
        monkeypatch.setattr(aelin_router._web_search, "search_and_fetch", lambda query, max_results=6, fetch_top_k=3: [row])

    _set_web_rows(
        "https://example.com/acme/release-1",
        "Acme 发布 1.0",
        "Acme 发布了 1.0，包含追踪功能。",
    )
    confirm = client.post(
        "/api/v1/aelin/track/confirm",
        json={"target": "Acme 发布", "source": "web", "query": "Acme 发布 最新"},
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text

    tracking_list = client.get("/api/v1/aelin/tracking?limit=20", headers=headers)
    assert tracking_list.status_code == 200, tracking_list.text
    items = tracking_list.json().get("items") or []
    assert items
    target_id = int(items[0]["target_id"])

    first_run = client.post(f"/api/v1/aelin/tracking/targets/{target_id}/run", headers=headers)
    assert first_run.status_code == 200, first_run.text
    assert bool(first_run.json().get("ok"))

    _set_web_rows(
        "https://example.com/acme/release-2",
        "Acme 发布 1.1",
        "Acme 发布了 1.1，新增了差分能力。",
    )
    second_run = client.post(f"/api/v1/aelin/tracking/targets/{target_id}/run", headers=headers)
    assert second_run.status_code == 200, second_run.text
    assert bool(second_run.json().get("ok"))

    changes_resp = client.get(f"/api/v1/aelin/tracking/targets/{target_id}/changes?limit=50", headers=headers)
    assert changes_resp.status_code == 200, changes_resp.text
    changes = changes_resp.json().get("items") or []
    assert changes
    unread_ids = [int(row["id"]) for row in changes if not bool(row.get("acked"))]
    assert unread_ids

    batch_ack = client.post(
        f"/api/v1/aelin/tracking/targets/{target_id}/changes/ack",
        json={"change_ids": unread_ids},
        headers=headers,
    )
    assert batch_ack.status_code == 200, batch_ack.text
    assert bool(batch_ack.json().get("ok"))
    assert str(batch_ack.json().get("message") or "").startswith("acked ")

    after_batch = client.get(f"/api/v1/aelin/tracking/targets/{target_id}/changes?limit=50", headers=headers)
    assert after_batch.status_code == 200, after_batch.text
    after_items = after_batch.json().get("items") or []
    acked_by_id = {int(row["id"]): bool(row.get("acked")) for row in after_items}
    for change_id in unread_ids:
        assert acked_by_id.get(change_id) is True

    single_id = int(unread_ids[0])
    single_ack = client.post(f"/api/v1/aelin/tracking/changes/{single_id}/ack", headers=headers)
    assert single_ack.status_code == 200, single_ack.text
    assert bool(single_ack.json().get("ok"))

    final_check = client.get(f"/api/v1/aelin/tracking/targets/{target_id}/changes?limit=10", headers=headers)
    assert final_check.status_code == 200, final_check.text
    final_by_id = {int(row["id"]): bool(row.get("acked")) for row in (final_check.json().get("items") or [])}
    assert final_by_id.get(single_id) is True


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

    confirm = client.post(
        "/api/v1/aelin/track/confirm",
        json={"target": "Notebook 周报", "source": "web", "query": "Notebook 周报"},
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text

    tracking_list = client.get("/api/v1/aelin/tracking?limit=20", headers=headers)
    assert tracking_list.status_code == 200, tracking_list.text
    target_id = int((tracking_list.json().get("items") or [])[0]["target_id"])
    run_resp = client.post(f"/api/v1/aelin/tracking/targets/{target_id}/run", headers=headers)
    assert run_resp.status_code == 200, run_resp.text

    search_resp = client.get(
        "/api/v1/aelin/tracking/file-memory/search",
        params={"workspace": "default", "query": "Notebook", "limit": 10},
        headers=headers,
    )
    assert search_resp.status_code == 200, search_resp.text
    items = search_resp.json().get("items") or []
    assert items
    path = str(items[0].get("path") or "")
    assert path

    content_resp = client.get(
        "/api/v1/aelin/tracking/file-memory/content",
        params={"workspace": "default", "path": path},
        headers=headers,
    )
    assert content_resp.status_code == 200, content_resp.text
    data = content_resp.json()
    assert data.get("path") == path
    assert isinstance(data.get("content"), str) and data.get("content")
    assert data.get("content").lstrip().startswith("#")

    tree_resp = client.get(
        "/api/v1/aelin/tracking/file-memory/tree",
        params={"workspace": "default", "max_files": 500},
        headers=headers,
    )
    assert tree_resp.status_code == 200, tree_resp.text
    tree_items = tree_resp.json().get("items") or []
    assert tree_items

    def _first_file(nodes: list[dict]) -> str:
        for node in nodes:
            if str(node.get("kind") or "") == "file":
                return str(node.get("path") or "")
            children = node.get("children") or []
            if isinstance(children, list):
                nested = _first_file(children)
                if nested:
                    return nested
        return ""

    rel_path = _first_file(tree_items)
    assert rel_path
    rel_content_resp = client.get(
        "/api/v1/aelin/tracking/file-memory/content",
        params={"workspace": "default", "path": rel_path},
        headers=headers,
    )
    assert rel_content_resp.status_code == 200, rel_content_resp.text
    rel_data = rel_content_resp.json()
    assert isinstance(rel_data.get("content"), str) and rel_data.get("content")


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
            "track_suggestion": {
                "target": "NBA 比赛",
                "source": "web",
                "reason": "你最近在问比赛结果，适合持续跟踪。",
            },
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
    assert "trace_agent" in trace_stages
    assert any((it.get("source") == "web") for it in data.get("citations") or [])
    assert any((it.get("kind") == "confirm_track") for it in data.get("actions") or [])


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
            "track_suggestion": None,
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


def test_aelin_chat_llm_planner_trace_route_not_overridden(monkeypatch):
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
            "tracking_intent": False,
            "ambiguities": [],
            "confidence": 0.9,
            "reason": "test_intent_chat",
            "intent_source": "llm",
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
            "track_suggestion": None,
            "route": {
                "reply_agent": True,
                "trace_agent": False,
                "allow_web_retry": False,
            },
            "reason": "test_planner_disable_trace",
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

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "Please track this topic for me", "use_memory": True, "workspace": "default"},
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
    assert not any((it.get("kind") == "confirm_track") for it in (data.get("actions") or []))


def test_aelin_chat_llm_planner_retry_not_overridden(monkeypatch):
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
            "tracking_intent": False,
            "ambiguities": [],
            "confidence": 0.9,
            "reason": "test_intent_chat",
            "intent_source": "llm",
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
            "track_suggestion": None,
            "route": {
                "reply_agent": True,
                "trace_agent": False,
                "allow_web_retry": False,
            },
            "reason": "test_planner_disable_retry",
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
        json={"query": "today warriors score", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert not any((it.get("source") == "web") for it in (data.get("citations") or []))
    web_step = next(
        (it for it in (data.get("tool_trace") or []) if (it.get("stage") == "web_search")),
        None,
    )
    assert isinstance(web_step, dict)
    assert web_step.get("status") == "skipped"


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
            "track_suggestion": None,
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
            "track_suggestion": None,
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
    assert aelin_router._is_time_sensitive_query("NBA最近打了什么比赛")
    assert aelin_router._is_sports_result_query("NBA最近打了什么比赛")


def test_diary_only_detection_covers_cn_and_en():
    assert aelin_router._is_diary_only_query("仅根据我在Aelinの日记里的记录回答：刚刚写入的内容讲了什么？")
    assert aelin_router._is_diary_only_query("Please only use my diary memory to answer this question.")
    assert not aelin_router._is_diary_only_query("NBA最近如何，顺便联网查一下")


def test_aelin_chat_diary_only_query_forces_no_web(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)
    call_state = {"web_calls": 0}

    monkeypatch.setattr(
        aelin_router,
        "_plan_tool_usage",
        lambda **kwargs: {
            "need_local_search": True,
            "need_web_search": True,
            "web_queries": ["抖音 内容 讲了什么"],
            "context_boundaries": [
                {"kind": "local", "query": "抖音 内容", "scope": "local"},
                {"kind": "web", "query": "抖音 内容 讲了什么", "scope": "web"},
            ],
            "track_suggestion": None,
            "route": {"reply_agent": True, "trace_agent": False, "allow_web_retry": True},
            "reason": "test_force_web_before_override",
        },
    )
    monkeypatch.setattr(
        aelin_router,
        "_build_planner_tracking_snapshot",
        lambda *args, **kwargs: {
            "active_items": [],
            "matched_items": [],
            "active_count": 0,
            "matched_count": 1,
            "matched_file_items": [
                {
                    "path": "D:/tmp/diary.md",
                    "title": "抖音内容摘要",
                    "preview": "这条记录显示该视频只提供了发布信息，未给出具体视频主题。",
                    "score": 12.5,
                    "updated_at": "2026-02-22T16:00:00+00:00",
                    "source": "douyin",
                    "kind": "insight",
                    "target": "抖音内容摘要",
                    "topic_path": "douyin",
                    "entry_kind": "media_insight",
                }
            ],
            "matched_file_count": 1,
        },
    )

    def _fake_web_search(query: str, max_results: int = 6, fetch_top_k: int = 3):
        call_state["web_calls"] += 1
        return [
            WebSearchResult(
                title="unexpected web result",
                url="https://example.com/web",
                snippet="unexpected",
                fetched_excerpt="unexpected",
            )
        ]

    monkeypatch.setattr(aelin_router._web_search, "search_and_fetch", _fake_web_search)

    resp = client.post(
        "/api/v1/aelin/chat",
        json={
            "query": "仅根据我在Aelinの日记里的记录回答：刚刚写入的那条抖音内容讲了什么？若信息不足请直说。",
            "use_memory": True,
            "workspace": "default",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert call_state["web_calls"] == 0
    assert isinstance(data.get("answer"), str) and data.get("answer")
    assert "日记" in str(data.get("answer") or "")
    assert not any((it.get("source") == "web") for it in (data.get("citations") or []))
    web_step = next((it for it in (data.get("tool_trace") or []) if (it.get("stage") == "web_search")), None)
    assert isinstance(web_step, dict)
    assert web_step.get("status") == "skipped"


def test_plan_tool_usage_invalid_json_fallback_still_dispatches_web():
    class _FakePlannerService:
        def is_configured(self) -> bool:
            return True

        def _chat(self, messages, max_tokens=420, stream=False):
            return "not a json payload"

    plan = aelin_router._plan_tool_usage(
        query="NBA最近打了什么比赛",
        service=_FakePlannerService(),
        provider="openai",
        memory_summary="有一些历史记忆",
        tracking_snapshot={"active_items": [], "matched_items": []},
    )
    assert plan.get("planner_source") == "fallback"
    assert plan.get("need_web_search") is True
    assert any((it.get("kind") == "web") for it in (plan.get("context_boundaries") or []))
    route = plan.get("route") or {}
    assert route.get("allow_web_retry") is True


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

    intent = aelin_router._build_intent_contract(
        query="nba recent results",
        service=_FakeService(),
        provider="openai",
        memory_summary="",
        tracking_snapshot={"active_count": 0, "matched_count": 0},
    )
    assert intent.get("intent_source") == "fallback"
    assert intent.get("requires_citations") is True
    assert intent.get("sports_result_intent") is True
    assert str(intent.get("time_scope") or "") in {"recent", "today"}


def test_plan_critic_can_patch_missing_web_path():
    class _FakeService:
        def is_configured(self) -> bool:
            return False

    critic = aelin_router._critic_tool_plan(
        query="nba recent results",
        intent_contract={
            "intent_type": "retrieval",
            "requires_citations": True,
            "sports_result_intent": True,
            "tracking_intent": False,
        },
        tool_plan={
            "need_local_search": True,
            "need_web_search": False,
            "web_queries": [],
            "context_boundaries": [{"kind": "local", "query": "nba", "scope": "local"}],
            "route": {"reply_agent": True, "trace_agent": False, "allow_web_retry": False},
        },
        service=_FakeService(),
        provider="rule_based",
    )
    assert critic.get("accepted") is False
    patch = critic.get("patch") or {}
    assert patch.get("need_web_search") is True
    assert isinstance(patch.get("web_queries"), list) and patch.get("web_queries")


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
            "tracking_intent": False,
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
            "track_suggestion": None,
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
            "tracking_intent": False,
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
            "track_suggestion": None,
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
            return {
                "workspace": bundle.get("workspace", workspace),
                "summary": bundle.get("summary", ""),
                "focus_items": [],
                "focus_items_raw": [],
                "notes": [],
                "notes_count": 0,
                "todos": bundle.get("todos", []),
                "pin_recommendations": bundle.get("pin_recommendations", []),
                "daily_brief": bundle.get("daily_brief"),
                "layout_cards": bundle.get("layout_cards", []),
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
    assert elapsed < 0.62
    stages = [str(it.get("stage") or "") for it in (resp.json().get("tool_trace") or [])]
    assert any(stage.startswith("local_search_subagent_") for stage in stages)


def test_aelin_chat_trace_agent_dispatches_local_and_web_subagents(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router,
        "_build_intent_contract",
        lambda **kwargs: {
            "goal": "tracking",
            "intent_type": "tracking",
            "time_scope": "recent",
            "freshness_hours": 24,
            "requires_citations": False,
            "requires_factuality": True,
            "sports_result_intent": False,
            "tracking_intent": True,
            "ambiguities": [],
            "confidence": 0.9,
            "reason": "test_intent_tracking",
            "intent_source": "llm",
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
            "trace_context_boundaries": [
                {"kind": "local", "query": "minimax memory", "scope": "memory"},
                {"kind": "web", "query": "minimax latest model release", "scope": "release"},
            ],
            "track_suggestion": {
                "target": "minimax 模型更新",
                "source": "web",
                "reason": "test_trace_dispatch",
            },
            "route": {"reply_agent": True, "trace_agent": True, "allow_web_retry": False},
            "reason": "test_trace_route",
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
    monkeypatch.setattr(
        aelin_router._web_search,
        "search_and_fetch",
        lambda query, max_results=6, fetch_top_k=3: [
            WebSearchResult(
                title=f"{query} - result",
                url=f"https://example.com/{abs(hash(query)) % 100000}",
                snippet="trace web result",
                fetched_excerpt="trace web result fetched excerpt",
            )
        ],
    )

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "帮我持续追踪 minimax 模型更新", "use_memory": True, "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    stages = [str(it.get("stage") or "") for it in (data.get("tool_trace") or [])]
    assert "trace_dispatch" in stages
    assert any(stage.startswith("trace_local_subagent_") for stage in stages)
    assert any(stage.startswith("trace_web_subagent_") for stage in stages)
    assert any((it.get("kind") == "confirm_track") for it in (data.get("actions") or []))


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
            "tracking_intent": False,
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
            "track_suggestion": None,
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
        json={"query": "please track today's nba result", "use_memory": True, "workspace": "default"},
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

def test_device_process_action_unsupported_returns_400():
    client = _create_test_client()
    headers = _auth_headers(client)

    resp = client.post(
        "/api/v1/aelin/device/processes/123/action",
        json={"action": "boom"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    data = resp.json().get("detail") or {}
    assert data.get("code") == "UNSUPPORTED_ACTION"
    assert "allowed_actions" in data


def test_device_capabilities_endpoint_contract():
    client = _create_test_client()
    headers = _auth_headers(client)

    resp = client.get("/api/v1/aelin/device/capabilities", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("platform"), str)
    caps = data.get("capabilities") or {}
    for key in [
        "process_list",
        "process_terminate",
        "process_priority",
        "mode_focus",
        "mode_silent",
        "mode_normal",
        "optimize_processes",
    ]:
        assert key in caps


def test_device_mode_apply_degraded_is_explicit():
    client = _create_test_client()
    headers = _auth_headers(client)

    resp = client.post(
        "/api/v1/aelin/device/mode/apply",
        json={"mode": "silent"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") in {"degraded", "partial"}
    assert isinstance(data.get("warnings"), list)
    assert data.get("warnings")


def test_device_processes_windows_fallback_without_psutil(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(device_center, "psutil", None)
    monkeypatch.setattr(device_center, "device_is_windows", lambda: True)
    monkeypatch.setattr(
        device_center,
        "run_powershell",
        lambda script, timeout_s=8: (
            True,
            json.dumps(
                [
                    {
                        "Name": "Code",
                        "ProcessName": "Code",
                        "Id": 1234,
                        "WorkingSet64": 734003200,
                        "CPU": 380.0,
                        "StartTime": "2026-02-20T10:00:00+08:00",
                        "PriorityClass": "Normal",
                    }
                ],
                ensure_ascii=False,
            ),
        ),
    )

    caps = client.get("/api/v1/aelin/device/capabilities", headers=headers)
    assert caps.status_code == 200, caps.text
    caps_data = caps.json()
    assert (caps_data.get("capabilities") or {}).get("process_list") is True

    resp = client.get("/api/v1/aelin/device/processes?sort_by=memory&limit=5", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("total", 0) >= 1
    first = (data.get("items") or [])[0]
    assert str(first.get("name") or "").lower().startswith("code")
    assert float(first.get("memory_mb") or 0.0) > 0

