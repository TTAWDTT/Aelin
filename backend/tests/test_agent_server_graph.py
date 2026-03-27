from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.deepagents.run_context import DeepAgentsRunContext


async def _open_graph(runtime):
    from agent_server.graph import make_graph

    async with make_graph(runtime) as graph:
        return graph


def test_agent_server_graph_factory_builds_placeholder_for_read_context():
    runtime = SimpleNamespace(
        access_context="assistants.read",
        execution_runtime=None,
        user=None,
    )

    graph = asyncio.run(_open_graph(runtime))

    assert hasattr(graph, "astream")
    assert hasattr(graph, "get_graph")


def test_agent_server_graph_factory_uses_execution_context(monkeypatch):
    import agent_server.graph as graph_module

    captured: dict[str, object] = {}

    def _fake_resolve_deepagents_runtime(
        db,
        *,
        user_id,
        workspace,
        raw_attachment_ids=None,
        cancel_checker=None,
        session_factory=None,
        allow_write_tools=None,
    ):  # noqa: ANN001
        _ = cancel_checker, allow_write_tools
        captured["db"] = db
        captured["user_id"] = user_id
        captured["workspace"] = workspace
        captured["attachment_ids"] = list(raw_attachment_ids or [])
        captured["session_factory"] = session_factory
        return SimpleNamespace(
            service=SimpleNamespace(),
            provider="openai",
            tool_context=SimpleNamespace(),
            limiter=SimpleNamespace(),
            memory_text="memory",
        )

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        captured["context_schema"] = kwargs.get("context_schema")
        return "compiled-graph", None, None, None

    monkeypatch.setattr(graph_module, "resolve_deepagents_runtime", _fake_resolve_deepagents_runtime)
    monkeypatch.setattr(graph_module, "build_chat_agent", _fake_build_chat_agent)

    runtime = SimpleNamespace(
        access_context="threads.create_run",
        execution_runtime=SimpleNamespace(
            context=DeepAgentsRunContext(
                user_id=7,
                workspace="demo",
                attachment_ids=[11, 12],
            )
        ),
        user=None,
    )

    graph = asyncio.run(_open_graph(runtime))

    assert graph == "compiled-graph"
    assert captured["user_id"] == 7
    assert captured["workspace"] == "demo"
    assert captured["attachment_ids"] == [11, 12]
    assert captured["context_schema"] is DeepAgentsRunContext


def test_agent_server_graph_factory_reads_dict_like_execution_context(monkeypatch):
    import agent_server.graph as graph_module

    captured: dict[str, object] = {}

    def _fake_resolve_deepagents_runtime(
        db,
        *,
        user_id,
        workspace,
        raw_attachment_ids=None,
        cancel_checker=None,
        session_factory=None,
        allow_write_tools=None,
    ):  # noqa: ANN001
        _ = db, cancel_checker, session_factory, allow_write_tools
        captured["user_id"] = user_id
        captured["workspace"] = workspace
        captured["attachment_ids"] = list(raw_attachment_ids or [])
        return SimpleNamespace(
            service=SimpleNamespace(),
            provider="openai",
            tool_context=SimpleNamespace(),
            limiter=SimpleNamespace(),
            memory_text="memory",
        )

    monkeypatch.setattr(graph_module, "resolve_deepagents_runtime", _fake_resolve_deepagents_runtime)
    monkeypatch.setattr(
        graph_module,
        "build_chat_agent",
        lambda **kwargs: ("compiled-graph", None, None, None),
    )

    runtime = SimpleNamespace(
        access_context="threads.create_run",
        execution_runtime=SimpleNamespace(
            context={
                "user_id": 9,
                "workspace": "dict-demo",
                "attachment_ids": [21, 22],
            }
        ),
        user={"user_id": 9},
    )

    graph = asyncio.run(_open_graph(runtime))

    assert graph == "compiled-graph"
    assert captured["user_id"] == 9
    assert captured["workspace"] == "dict-demo"
    assert captured["attachment_ids"] == [21, 22]
