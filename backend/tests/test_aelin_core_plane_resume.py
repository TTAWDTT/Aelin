from __future__ import annotations

from types import SimpleNamespace

import app.services.aelin_core as aelin_core
from app.schemas import AelinChatRequest
from app.services.aelin_loop_types import AelinAgentLoopResult


class _FakeConfiguredService:
    def __init__(self) -> None:
        self.config = SimpleNamespace(model="fake-model", temperature=0.0, web_search_proxy_url="")
        self.client = object()

    def is_configured(self) -> bool:
        return True


class _FakeToolHub:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def tool_definitions(self) -> list[dict]:
        return [
            {"type": "function", "function": {"name": "plane", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "context_get", "parameters": {"type": "object"}}},
        ]

    def execute(self, name: str, args: dict) -> dict:
        return {"ok": True}


def _reset_runner() -> None:
    # No-op in the DeepAgents-only runtime; plane resume tests now track calls
    # via the local `calls` list inside the test body instead of a fake loop
    # class. This helper is kept only to satisfy legacy imports.
    return None


def test_try_agent_loop_chat_only_injects_active_plane_for_related_query(monkeypatch):
    _reset_runner()
    monkeypatch.setattr(aelin_core, "_resolve_llm_service", lambda db, user: (_FakeConfiguredService(), "openai"))
    monkeypatch.setattr(aelin_core, "_get_memory_summary_for_chat", lambda db, user_id, workspace="default": "summary")
    monkeypatch.setattr(aelin_core, "AelinToolHub", _FakeToolHub)

    calls: list[dict] = []

    def _fake_run_loop(**kwargs):
        calls.append(dict(kwargs))
        return AelinAgentLoopResult(
            ok=True,
            answer="ok",
            stop_reason="final_answer",
            rounds=1,
            total_calls=0,
            write_calls=0,
            tool_runs=[],
            trace_steps=[],
            actions=[],
            error="",
            memory_snapshot="",
        )

    monkeypatch.setattr(aelin_core, "run_deepagents_loop", _fake_run_loop)
    monkeypatch.setattr(
        aelin_core,
        "get_active_plane_task",
        lambda user_id, workspace, plane="browser", db=None: {
            "task_id": "browser-task-1",
            "state": "waiting_user",
            "goal": "帮我查看淘宝订单",
            "user_prompt": "请先完成登录",
            "last_url": "https://www.taobao.com/member",
            "plane": "browser",
        },
    )

    unrelated_payload = AelinChatRequest(query="今天的新闻有什么", workspace="default")
    related_payload = AelinChatRequest(query="我已经登录好了", workspace="default")

    unrelated = aelin_core._try_agent_loop_chat(
        unrelated_payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
        persist_memory=False,
    )
    related = aelin_core._try_agent_loop_chat(
        related_payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
        persist_memory=False,
    )

    assert unrelated is not None
    assert related is not None
    assert len(calls) == 2
    # DeepAgents path should only receive a plane_snapshot for the related query.
    assert calls[0]["plane_snapshot"] is None
    assert isinstance(calls[1]["plane_snapshot"], dict)
    assert calls[1]["plane_snapshot"]["task_id"] == "browser-task-1"
