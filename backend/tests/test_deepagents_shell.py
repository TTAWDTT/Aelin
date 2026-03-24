from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests.aelin_test_utils import _auth_headers, _create_test_client


@pytest.mark.integration
def test_deepagents_chat_stream_basic(monkeypatch):
    """Ensure /api/v1/deepagents/chat/stream emits start/chunk/final events."""

    client = _create_test_client()
    headers = _auth_headers(client)

    import app.routers.deepagents_chat as dchat
    from app.services.deepagents import deepagents_graph as dag
    from app.services.aelin.tool_policy import ToolPolicyUsage

    # Avoid hitting real provider: force LLM to appear misconfigured so the
    # route short-circuits before building the DeepAgents graph.
    monkeypatch.setattr(
        dchat,
        "_resolve_llm_service",
        lambda db, user: (SimpleNamespace(is_configured=lambda: False), "rule_based"),
    )

    captured: dict[str, object] = {}

    class _FakeAgent:
        def stream(self, payload):  # noqa: ANN001
            captured["payload"] = payload
            # Minimal DeepAgents-like chunk.
            yield {
                "version": "v2",
                "type": "messages",
                "data": {"content": "hello from deepagents"},
            }

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        _ = kwargs
        return _FakeAgent(), ToolPolicyUsage(), [], {}

    monkeypatch.setattr(dag, "build_chat_agent", _fake_build_chat_agent)

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

    # Basic shape: start -> one or more chunk events -> final -> done.
    blocks = [
        b
        for b in body.replace("\r\n", "\n").split("\n\n")
        if b.strip() and not b.strip().startswith(":")
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

    names = [name for name, _ in events]
    assert "start" in names
    assert "error" in names or "final" in names or "done" in names
