from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_stream_idle_timeout_uses_model_node_budget_floor(monkeypatch):
    from app.services.deepagents.timeout_policy import read_stream_idle_timeout_seconds
    from app.settings import settings

    monkeypatch.setattr(settings, "deepagents_stream_idle_timeout_seconds", 45.0)
    monkeypatch.setattr(settings, "deepagents_run_timeout_seconds", 120.0)

    assert read_stream_idle_timeout_seconds(request_timeout_seconds=180.0) == 120.0


def test_select_tool_timeout_seconds_uses_layered_budgets(monkeypatch):
    from app.services.deepagents.timeout_policy import select_tool_timeout_seconds
    from app.settings import settings

    monkeypatch.setattr(settings, "deepagents_tool_timeout_seconds_fast", 30.0)
    monkeypatch.setattr(settings, "deepagents_tool_timeout_seconds_io", 90.0)
    monkeypatch.setattr(settings, "deepagents_tool_timeout_seconds_execute", 180.0)

    assert select_tool_timeout_seconds(name="memory_search") == 30.0
    assert select_tool_timeout_seconds(name="web_search") == 90.0
    assert select_tool_timeout_seconds(name="execute", args={"timeout_ms": 120000}) == 180.0
    assert select_tool_timeout_seconds(name="execute", remaining_budget_seconds=18.0) == 18.0


def test_model_timeout_middleware_respects_run_budget_before_node_timeout():
    from app.services.deepagents.model_timeout_middleware import DeepAgentsModelTimeoutMiddleware

    middleware = DeepAgentsModelTimeoutMiddleware(
        timeout_seconds=180.0,
        run_budget_seconds=0.05,
        run_started_monotonic=0.0,
    )

    async def _handler(_request):  # noqa: ANN001
        await asyncio.sleep(0.2)
        return {"ok": True}

    request = SimpleNamespace(
        runtime=SimpleNamespace(context={"user_id": 1, "workspace": "default"}),
        model=SimpleNamespace(model_name="fake-model"),
        tools=[],
        messages=[],
        system_message=None,
    )

    response = asyncio.run(middleware.awrap_model_call(request, _handler))

    assert "总运行预算" in str(getattr(response, "content", ""))
