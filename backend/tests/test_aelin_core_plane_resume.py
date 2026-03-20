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


class _FakeRunner:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def run(self, **kwargs):
        _FakeRunner.calls.append(dict(kwargs))
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


def _reset_runner() -> None:
    _FakeRunner.calls.clear()


def test_try_agent_loop_chat_only_injects_active_plane_for_related_query(monkeypatch):
    _reset_runner()
    monkeypatch.setattr(aelin_core, "_resolve_llm_service", lambda db, user: (_FakeConfiguredService(), "openai"))
    monkeypatch.setattr(aelin_core, "_get_memory_summary_for_chat", lambda db, user_id: "summary")
    monkeypatch.setattr(aelin_core, "AelinToolHub", _FakeToolHub)
    monkeypatch.setattr(aelin_core, "AelinAgentLoop", _FakeRunner)
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
    assert len(_FakeRunner.calls) == 2
    assert _FakeRunner.calls[0]["forced_tool_runs"] == []
    assert _FakeRunner.calls[1]["forced_tool_runs"]
    injected = _FakeRunner.calls[1]["forced_tool_runs"][0]
    assert injected["name"] == "plane"
    assert injected["args"]["action"] == "status"
    assert injected["args"]["task_id"] == "browser-task-1"
