from __future__ import annotations

import json
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

from tests.aelin_test_utils import _auth_headers, _create_test_client


def _parse_sse_events(body: str) -> list[tuple[str, dict]]:
    blocks = [
        block
        for block in body.replace("\r\n", "\n").split("\n\n")
        if block.strip() and not block.strip().startswith(":")
    ]
    events: list[tuple[str, dict]] = []
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
            events.append((event, json.loads(data_line)))
        except Exception:
            continue
    return events


@pytest.mark.integration
def test_deepagents_chat_stream_basic(monkeypatch):
    """Ensure /api/v1/deepagents/chat/stream emits near-native v2 events."""

    client = _create_test_client()
    headers = _auth_headers(client)

    import app.routers.deepagents_chat as dchat
    from app.services.deepagents import deepagents_graph as dag
    from app.services.deepagents.tool_runtime import ToolPolicyUsage

    monkeypatch.setattr(
        dchat,
        "_resolve_llm_service",
        lambda db, user: (SimpleNamespace(is_configured=lambda: True, config=SimpleNamespace(web_search_proxy_url="")), "openai"),
    )
    monkeypatch.setattr(dchat, "_get_agents_memory_text_for_chat", lambda db, user_id, workspace: "")
    monkeypatch.setattr(dchat, "_scoped_web_search_service", lambda proxy_url: None)
    monkeypatch.setattr(
        dchat,
        "_serialize_agent_topology",
        lambda agent: {
            "nodes": [
                {"id": "__start__", "name": "__start__", "kind": "start"},
                {"id": "model", "name": "model", "kind": "model"},
                {"id": "tools", "name": "tools", "kind": "tools"},
                {"id": "__end__", "name": "__end__", "kind": "end"},
            ],
            "edges": [
                {"source": "__start__", "target": "model", "conditional": False},
                {"source": "model", "target": "tools", "conditional": True},
                {"source": "tools", "target": "__end__", "conditional": True},
            ],
        },
    )

    captured: dict[str, object] = {}

    class _FakeAgent:
        def stream(self, payload, **kwargs):  # noqa: ANN001
            captured["payload"] = payload
            captured["stream_kwargs"] = kwargs
            yield {
                "type": "messages",
                "ns": ["root", "model"],
                "data": (
                    SimpleNamespace(id="msg-1", type="ai", content="hello from deepagents"),
                    {"langgraph_node": "model"},
                ),
            }
            yield {
                "type": "updates",
                "ns": ["root"],
                "data": {"model": {"status": "running"}},
            }
            yield {
                "type": "tasks",
                "ns": ["root"],
                "data": {
                    "id": "task-1",
                    "name": "tools",
                    "status": "completed",
                    "input": {
                        "__type": "tool_call_with_context",
                        "tool_call": {
                            "name": "web_search",
                            "id": "call-1",
                            "args": {
                                "query": "today shanghai weather",
                                "max_results": 5,
                            },
                        },
                    },
                    "result": {
                        "ok": True,
                        "total": 2,
                        "query": "today shanghai weather",
                    },
                },
            }
            yield {
                "type": "values",
                "ns": ["root"],
                "data": {
                    "messages": [{"role": "assistant", "content": "hello from deepagents"}],
                    "files": {"/memory/AGENTS.md": {"content": ["secret"]}},
                    "todos": [{"title": "todo-1"}],
                },
            }

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        _ = kwargs
        return _FakeAgent(), ToolPolicyUsage(), [], {}

    monkeypatch.setattr(dag, "build_chat_agent", _fake_build_chat_agent)
    monkeypatch.setattr(dchat, "build_chat_agent", _fake_build_chat_agent)

    with client.stream(
        "POST",
        "/api/v1/deepagents/chat/stream",
        json={
            "query": "ping",
            "use_memory": False,
            "workspace": "default",
            "images": [],
        },
        headers=headers,
    ) as resp:
        assert resp.status_code == 200, resp.text
        body = "".join(resp.iter_text())

    events = _parse_sse_events(body)
    names = [name for name, _ in events]
    assert "metadata" in names
    assert "messages|root|model" in names
    assert "updates|root" in names
    assert "tasks|root" in names
    assert "values|root" in names

    metadata_payload = next(payload for name, payload in events if name == "metadata")
    assert isinstance(metadata_payload["run_id"], str) and metadata_payload["run_id"]

    topology_payload = next(
        payload
        for name, payload in events
        if name == "values|root" and isinstance(payload, dict) and "topology" in payload
    )
    assert topology_payload["topology"]["nodes"][0]["id"] == "__start__"
    assert topology_payload["topology"]["edges"][0]["target"] == "model"

    message_payload = next(payload for name, payload in events if name == "messages|root|model")
    assert isinstance(message_payload, list) and len(message_payload) == 2
    assert message_payload[0]["id"] == "msg-1"
    assert message_payload[0]["type"] == "ai"
    assert message_payload[0]["content"] == "hello from deepagents"
    assert message_payload[1]["langgraph_node"] == "model"
    assert message_payload[1]["langgraph_checkpoint_ns"] == "root|model"

    task_payload = next(payload for name, payload in events if name == "tasks|root")
    assert task_payload["name"] == "tools"
    assert task_payload["input"]["tool_call"]["name"] == "web_search"
    assert task_payload["input"]["tool_call"]["id"] == "call-1"
    assert task_payload["input"]["tool_call"]["args"]["query"] == "today shanghai weather"
    assert "files" not in task_payload
    assert task_payload["result"]["query"] == "today shanghai weather"

    values_payload = next(
        payload
        for name, payload in events
        if name == "values|root" and isinstance(payload, dict) and "messages" in payload
    )
    assert values_payload["messages"][0]["content"] == "hello from deepagents"
    assert values_payload["todos"][0]["title"] == "todo-1"
    assert "files" not in values_payload
    assert captured["stream_kwargs"] == {
        "stream_mode": ["messages", "updates", "tasks", "values"],
        "version": "v2",
        "subgraphs": True,
    }


@pytest.mark.integration
def test_deepagents_chat_stream_accepts_pydantic_history(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    import app.routers.deepagents_chat as dchat
    from app.services.deepagents import deepagents_graph as dag
    from app.services.deepagents.tool_runtime import ToolPolicyUsage

    monkeypatch.setattr(
        dchat,
        "_resolve_llm_service",
        lambda db, user: (SimpleNamespace(is_configured=lambda: True, config=SimpleNamespace(web_search_proxy_url="")), "openai"),
    )
    monkeypatch.setattr(dchat, "_get_agents_memory_text_for_chat", lambda db, user_id, workspace: "")
    monkeypatch.setattr(dchat, "_scoped_web_search_service", lambda proxy_url: None)

    captured: dict[str, object] = {}

    class _FakeAgent:
        def stream(self, payload, **kwargs):  # noqa: ANN001
            captured["payload"] = payload
            captured["stream_kwargs"] = kwargs
            yield {
                "type": "messages",
                "ns": ["root", "model"],
                "data": (SimpleNamespace(content="ok"), {"langgraph_node": "model"}),
            }
            yield {
                "type": "values",
                "ns": ["root"],
                "data": {"messages": [{"role": "assistant", "content": "ok"}]},
            }

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        _ = kwargs
        return _FakeAgent(), ToolPolicyUsage(), [], {}

    monkeypatch.setattr(dag, "build_chat_agent", _fake_build_chat_agent)
    monkeypatch.setattr(dchat, "build_chat_agent", _fake_build_chat_agent)

    with client.stream(
        "POST",
        "/api/v1/deepagents/chat/stream",
        json={
            "query": "你好呀",
            "use_memory": False,
            "workspace": "default",
            "history": [
                {"role": "user", "content": "上一轮问题"},
                {"role": "assistant", "content": "上一轮回答"},
            ],
        },
        headers=headers,
    ) as resp:
        assert resp.status_code == 200, resp.text
        _ = "".join(resp.iter_text())

    payload = captured.get("payload")
    assert isinstance(payload, dict)
    messages = payload.get("messages")
    assert isinstance(messages, list)
    assert messages[0] == {"role": "user", "content": "上一轮问题"}
    assert messages[1] == {"role": "assistant", "content": "上一轮回答"}
    assert messages[-1] == {"role": "user", "content": "你好呀"}
    assert captured["stream_kwargs"] == {
        "stream_mode": ["messages", "updates", "tasks", "values"],
        "version": "v2",
        "subgraphs": True,
    }


def test_build_chat_agent_injects_current_date_into_system_prompt(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    captured: dict[str, object] = {}

    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())

    def _fake_create_deep_agent(**kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    agent, usage, tool_runs, files_mapping = dag.build_chat_agent(
        service=SimpleNamespace(),
        provider="openai",
        context=SimpleNamespace(),
        limiter=SimpleNamespace(),
        memory_text="",
        cancel_token=None,
    )

    assert agent is not None
    assert usage is not None
    assert tool_runs == []
    assert isinstance(files_mapping, dict)

    system_prompt = str(captured.get("system_prompt") or "")
    assert "Current date:" in system_prompt
    assert "Current timezone: Asia/Shanghai." in system_prompt
    assert "Interpret relative date and time references" in system_prompt


def test_skill_mount_snapshot_uses_process_cache(monkeypatch, tmp_path):
    from app.services.deepagents import deepagents_graph as dag

    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "sample-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Sample\n", encoding="utf-8")
    (skill_dir / "notes.md").write_text("hello", encoding="utf-8")

    original_read_text = Path.read_text
    read_count = {"value": 0}

    def _counting_read_text(self, *args, **kwargs):  # noqa: ANN001
        if str(self).startswith(str(tmp_path)):
            read_count["value"] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    key = (str(skills_root.resolve()), "")
    with dag._SKILL_MOUNT_CACHE_LOCK:
        dag._SKILL_MOUNT_CACHE.pop(key, None)

    first = dag._get_skill_mount_snapshot(skills_root, "")
    second = dag._get_skill_mount_snapshot(skills_root, "")

    assert first is second
    assert read_count["value"] == 2
    assert "/skills/aelin/sample-skill/SKILL.md" in first.skill_files

    with dag._SKILL_MOUNT_CACHE_LOCK:
        dag._SKILL_MOUNT_CACHE.pop(key, None)


@pytest.mark.integration
def test_deepagents_chat_stream_worker_uses_owned_session(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    import app.routers.deepagents_chat as dchat
    from app.services.deepagents.tool_runtime import ToolPolicyUsage

    worker_session = SimpleNamespace(closed=False)
    captured: dict[str, object] = {}

    def _fake_close():
        worker_session.closed = True

    worker_session.close = _fake_close

    monkeypatch.setattr(dchat, "create_session", lambda: worker_session)
    def _fake_resolve_llm_service(db, user):  # noqa: ANN001
        _ = user
        captured["db"] = db
        return (
            SimpleNamespace(
                is_configured=lambda: True,
                config=SimpleNamespace(web_search_proxy_url=""),
            ),
            "openai",
        )

    monkeypatch.setattr(dchat, "_resolve_llm_service", _fake_resolve_llm_service)
    monkeypatch.setattr(dchat, "_get_agents_memory_text_for_chat", lambda db, user_id, workspace: "")
    monkeypatch.setattr(dchat, "_scoped_web_search_service", lambda proxy_url: None)
    monkeypatch.setattr(dchat, "_serialize_agent_topology", lambda agent: None)

    class _FakeAgent:
        def stream(self, payload, **kwargs):  # noqa: ANN001
            _ = payload, kwargs
            yield {
                "type": "values",
                "ns": ["root"],
                "data": {"messages": [{"role": "assistant", "content": "ok"}]},
            }

    monkeypatch.setattr(
        dchat,
        "build_chat_agent",
        lambda **kwargs: (_FakeAgent(), ToolPolicyUsage(), [], {}),
    )

    with client.stream(
        "POST",
        "/api/v1/deepagents/chat/stream",
        json={"query": "ping", "use_memory": False, "workspace": "default"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200, resp.text
        _ = "".join(resp.iter_text())

    assert captured["db"] is worker_session
    assert worker_session.closed is True


def test_tool_attachment_search_uses_fresh_session_factory():
    from app.services.tools.tools_files import tool_attachment_search

    calls: list[str] = []

    class _FakeSession:
        def close(self):
            calls.append("close")

    class _FakeAttachmentService:
        def search(self, db, **kwargs):  # noqa: ANN001
            calls.append("search")
            assert isinstance(db, _FakeSession)
            assert kwargs["query"] == "needle"
            return {
                "ok": True,
                "total": 1,
                "content": "hit",
                "hits": [{"text": "hit"}],
                "attachment_ids": [7],
            }

    def _session_factory():
        calls.append("open")
        return _FakeSession()

    result = tool_attachment_search(
        SimpleNamespace(
            attachment_service=_FakeAttachmentService(),
            available_attachment_ids=[7],
            session_factory=_session_factory,
            user_id=1,
            workspace="default",
        ),
        {"query": "needle", "attachment_ids": [7]},
    )

    assert result["ok"] is True
    assert calls == ["open", "search", "close"]


@pytest.mark.integration
def test_deepagents_chat_stream_filters_draft_tool_calls_without_tool_run_custom_event(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    import app.routers.deepagents_chat as dchat
    from app.services.deepagents import deepagents_graph as dag
    from app.services.deepagents.tool_runtime import ToolPolicyUsage

    monkeypatch.setattr(
        dchat,
        "_resolve_llm_service",
        lambda db, user: (SimpleNamespace(is_configured=lambda: True, config=SimpleNamespace(web_search_proxy_url="")), "openai"),
    )
    monkeypatch.setattr(dchat, "_get_agents_memory_text_for_chat", lambda db, user_id, workspace: "")
    monkeypatch.setattr(dchat, "_scoped_web_search_service", lambda proxy_url: None)
    monkeypatch.setattr(dchat, "_serialize_agent_topology", lambda agent: None)

    class _FakeAgent:
        def stream(self, payload, **kwargs):  # noqa: ANN001
            _ = payload, kwargs
            yield {
                "type": "messages",
                "ns": ["root", "model"],
                "data": (
                    {
                        "id": "msg-tools",
                        "type": "ai",
                        "content": "",
                        "tool_calls": [
                            {"id": "", "name": "web_search", "args": {"query": "draft"}},
                            {"id": "call-keep", "name": "web_search", "args": {"query": "stable"}},
                        ],
                    },
                    {"langgraph_node": "model"},
                ),
            }
            yield {
                "type": "values",
                "ns": ["root"],
                "data": {"messages": [{"role": "assistant", "content": "done"}]},
            }

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        tool_event_cb = kwargs.get("tool_event_cb")
        if callable(tool_event_cb):
            tool_event_cb(
                {
                    "key": "web_search:1",
                    "name": "web_search",
                    "args": {"query": "stable"},
                    "state": "completed",
                    "result": {"ok": True, "total": 1},
                    "error": "",
                    "latency_ms": 12,
                }
            )
        return _FakeAgent(), ToolPolicyUsage(), [], {}

    monkeypatch.setattr(dag, "build_chat_agent", _fake_build_chat_agent)
    monkeypatch.setattr(dchat, "build_chat_agent", _fake_build_chat_agent)

    with client.stream(
        "POST",
        "/api/v1/deepagents/chat/stream",
        json={"query": "test", "use_memory": False, "workspace": "default"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200, resp.text
        body = "".join(resp.iter_text())

    events = _parse_sse_events(body)
    custom_events = [payload for name, payload in events if name == "custom"]
    assert not any(payload.get("kind") == "tool_run" for payload in custom_events)

    message_payload = next(payload for name, payload in events if name == "messages|root|model")
    assert len(message_payload[0]["tool_calls"]) == 1
    assert message_payload[0]["tool_calls"][0]["id"] == "call-keep"
    assert message_payload[0]["tool_calls"][0]["args"]["query"] == "stable"


def test_sanitize_tool_call_drops_empty_json_string_args():
    import app.routers.deepagents_chat as dchat

    assert dchat._sanitize_tool_call(
        {"id": "call-1", "name": "web_search", "args": "{}"}
    ) is None
    assert dchat._sanitize_tool_call(
        {"id": "call-1", "name": "web_search", "args": "[]"}
    ) is None
    assert dchat._sanitize_tool_call(
        {"id": "call-1", "name": "web_search", "args": "null"}
    ) is None


def test_invoke_tool_timeout_marks_write_unknown_and_uses_bounded_executor(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag
    from app.services.deepagents import tool_runtime as tr

    monkeypatch.setattr(dag.settings, "deepagents_tool_timeout_seconds", 1.0, raising=False)
    tr._reset_tool_executor_for_tests(max_workers=1)

    limiter = tr.ToolCallLimiter(
        max_tool_calls=10,
        max_write_calls=10,
        allow_write_tools=True,
        consecutive_failures_limit=3,
        consecutive_no_progress_limit=2,
    )
    usage = tr.ToolPolicyUsage()
    tool_runs: list[dict[str, object]] = []

    def _slow_write(_context, _args):  # noqa: ANN001
        time.sleep(2.0)
        return {"ok": True, "opened": True}

    try:
        first = dag._invoke_tool(
            name="device",
            args={"action": "open_url", "url": "https://example.com"},
            handler=_slow_write,
            context=SimpleNamespace(),
            limiter=limiter,
            usage=usage,
            tool_runs=tool_runs,
        )
        assert first["ok"] is False
        assert first["stop_retry"] is True
        assert first["maybe_applied"] is True
        assert "do not retry the same write blindly" in str(first["error"])

        second = dag._invoke_tool(
            name="device",
            args={"action": "open_url", "url": "https://example.org"},
            handler=_slow_write,
            context=SimpleNamespace(),
            limiter=limiter,
            usage=usage,
            tool_runs=tool_runs,
        )
        assert second["ok"] is False
        assert second["stop_retry"] is True
        assert "previous long-running tool calls are still draining" in str(second["error"])
    finally:
        time.sleep(1.2)
        tr._reset_tool_executor_for_tests(max_workers=4)


@pytest.mark.integration
def test_deepagents_chat_stream_emits_idle_timeout_and_done(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    import app.routers.deepagents_chat as dchat
    from app.services.deepagents import deepagents_graph as dag
    from app.services.deepagents.tool_runtime import ToolPolicyUsage

    monkeypatch.setattr(
        dchat,
        "_resolve_llm_service",
        lambda db, user: (
            SimpleNamespace(
                is_configured=lambda: True,
                config=SimpleNamespace(web_search_proxy_url=""),
            ),
            "openai",
        ),
    )
    monkeypatch.setattr(dchat, "_get_agents_memory_text_for_chat", lambda db, user_id, workspace: "")
    monkeypatch.setattr(dchat, "_scoped_web_search_service", lambda proxy_url: None)
    monkeypatch.setattr(dchat, "_serialize_agent_topology", lambda agent: None)
    monkeypatch.setattr(dchat.settings, "deepagents_stream_idle_timeout_seconds", 0.1, raising=False)
    monkeypatch.setattr(dchat.settings, "deepagents_run_timeout_seconds", 30.0, raising=False)

    class _FakeAgent:
        def stream(self, payload, **kwargs):  # noqa: ANN001
            _ = payload, kwargs
            time.sleep(6.0)
            if False:
                yield {}

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        _ = kwargs
        return _FakeAgent(), ToolPolicyUsage(), [], {}

    monkeypatch.setattr(dag, "build_chat_agent", _fake_build_chat_agent)
    monkeypatch.setattr(dchat, "build_chat_agent", _fake_build_chat_agent)

    with client.stream(
        "POST",
        "/api/v1/deepagents/chat/stream",
        json={"query": "timeout test", "use_memory": False, "workspace": "default"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200, resp.text
        body = "".join(resp.iter_text())

    events = _parse_sse_events(body)
    error_payload = next(payload for name, payload in events if name == "error")
    done_payload = next(payload for name, payload in events if name == "done")

    assert "deepagents_run_idle_timeout" in str(error_payload.get("message") or "")
    assert done_payload["status"] == "__done__"


@pytest.mark.integration
def test_deepagents_chat_stream_does_not_idle_timeout_while_tool_is_running(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    import app.routers.deepagents_chat as dchat
    from app.services.deepagents import deepagents_graph as dag
    from app.services.deepagents.tool_runtime import ToolPolicyUsage

    monkeypatch.setattr(
        dchat,
        "_resolve_llm_service",
        lambda db, user: (
            SimpleNamespace(
                is_configured=lambda: True,
                config=SimpleNamespace(web_search_proxy_url=""),
            ),
            "openai",
        ),
    )
    monkeypatch.setattr(dchat, "_get_agents_memory_text_for_chat", lambda db, user_id, workspace: "")
    monkeypatch.setattr(dchat, "_scoped_web_search_service", lambda proxy_url: None)
    monkeypatch.setattr(dchat, "_serialize_agent_topology", lambda agent: None)
    monkeypatch.setattr(dchat.settings, "deepagents_stream_idle_timeout_seconds", 0.1, raising=False)
    monkeypatch.setattr(dchat.settings, "deepagents_run_timeout_seconds", 30.0, raising=False)

    class _FakeAgent:
        def stream(self, payload, **kwargs):  # noqa: ANN001
            tool_event_cb = kwargs.pop("_tool_event_cb")
            _ = payload, kwargs
            tool_event_cb(
                {
                    "key": "web_search:1",
                    "name": "web_search",
                    "args": {"query": "github trending"},
                    "state": "running",
                    "result": {},
                    "error": "",
                    "latency_ms": 0,
                }
            )
            time.sleep(0.35)
            tool_event_cb(
                {
                    "key": "web_search:1",
                    "name": "web_search",
                    "args": {"query": "github trending"},
                    "state": "completed",
                    "result": {"ok": True, "total": 1},
                    "error": "",
                    "latency_ms": 350,
                }
            )
            yield {
                "type": "values",
                "ns": ["root"],
                "data": {"messages": [{"role": "assistant", "content": "ok"}]},
            }

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        tool_event_cb = kwargs.get("tool_event_cb")

        class _WrappedAgent(_FakeAgent):
            def stream(self, payload, **stream_kwargs):  # noqa: ANN001
                return super().stream(payload, _tool_event_cb=tool_event_cb, **stream_kwargs)

        return _WrappedAgent(), ToolPolicyUsage(), [], {}

    monkeypatch.setattr(dag, "build_chat_agent", _fake_build_chat_agent)
    monkeypatch.setattr(dchat, "build_chat_agent", _fake_build_chat_agent)

    with client.stream(
        "POST",
        "/api/v1/deepagents/chat/stream",
        json={"query": "tool running timeout test", "use_memory": False, "workspace": "default"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200, resp.text
        body = "".join(resp.iter_text())

    events = _parse_sse_events(body)
    names = [name for name, _ in events]
    assert "error" not in names
    assert "done" in names
    values_payload = next(payload for name, payload in events if name == "values|root")
    assert values_payload["messages"][0]["content"] == "ok"
