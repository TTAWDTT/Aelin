from __future__ import annotations

import json
from types import SimpleNamespace

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
    """Ensure /api/v1/deepagents/chat/stream emits native v2 events."""

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
                "data": (
                    SimpleNamespace(content="hello from deepagents"),
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
    assert "start" in names
    assert "messages" in names
    assert "updates" in names
    assert "tasks" in names
    assert "values" in names
    assert "final" in names

    message_payload = next(payload for name, payload in events if name == "messages")
    assert message_payload["type"] == "messages"
    assert isinstance(message_payload["run_id"], str) and message_payload["run_id"]
    assert isinstance(message_payload["seq"], int) and message_payload["seq"] > 0
    assert message_payload["ns"] == ["root", "model"]
    assert message_payload["data"]["content"] == "hello from deepagents"
    assert message_payload["data"]["metadata"]["langgraph_node"] == "model"

    task_payload = next(payload for name, payload in events if name == "tasks")
    assert task_payload["data"]["name"] == "tools"
    assert task_payload["data"]["tool_name"] == "web_search"
    assert task_payload["data"]["tool_call"]["id"] == "call-1"
    assert task_payload["data"]["tool_call"]["args"]["query"] == "today shanghai weather"
    assert "files" not in task_payload["data"]
    assert "result_summary" in task_payload["data"]

    values_payload = next(payload for name, payload in events if name == "values")
    assert values_payload["data"]["messages_count"] == 1
    assert values_payload["data"]["todos_count"] == 1
    assert values_payload["data"]["answer"] == "hello from deepagents"
    assert "files" not in values_payload["data"]

    final_payload = next(payload for name, payload in events if name == "final")
    assert final_payload["type"] == "final"
    assert final_payload["data"]["answer"] == "hello from deepagents"
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
