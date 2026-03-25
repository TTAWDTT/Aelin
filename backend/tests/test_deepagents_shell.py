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
    """Ensure /api/v1/deepagents/chat/stream emits native v2 events plus compatibility events."""

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
                "data": {"id": "task-1", "name": "web_search", "status": "completed"},
            }
            yield {
                "type": "values",
                "ns": ["root"],
                "data": {"messages": [{"role": "assistant", "content": "hello from deepagents"}]},
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
    assert "reply" in names
    assert "final" in names

    message_payload = next(payload for name, payload in events if name == "messages")
    assert message_payload["type"] == "messages"
    assert message_payload["ns"] == ["root", "model"]
    assert message_payload["data"]["content"] == "hello from deepagents"
    assert message_payload["data"]["metadata"]["langgraph_node"] == "model"

    final_payload = next(payload for name, payload in events if name == "final")
    assert final_payload["answer"] == "hello from deepagents"
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
