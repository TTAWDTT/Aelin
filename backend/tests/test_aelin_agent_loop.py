from __future__ import annotations

import copy
import threading
import time
from types import SimpleNamespace
from typing import Any

from app.services.aelin_agent_loop import AelinAgentLoop
from app.services.aelin_tool_policy import AelinToolPolicy


class _FakeCompletions:
    def __init__(self, rounds: list[dict[str, Any]]) -> None:
        self._rounds = list(rounds)
        self._idx = 0
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        idx = min(self._idx, len(self._rounds) - 1)
        self._idx += 1
        row = self._rounds[idx]
        tool_calls = []
        for tc in row.get("tool_calls", []):
            tool_calls.append(
                SimpleNamespace(
                    id=str(tc.get("id") or ""),
                    function=SimpleNamespace(
                        name=str(tc.get("name") or ""),
                        arguments=str(tc.get("arguments") or "{}"),
                    ),
                )
            )
        msg = SimpleNamespace(content=str(row.get("content") or ""), tool_calls=tool_calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeToolHub:
    def __init__(self, *, sleep_seconds: float = 0.15) -> None:
        self.workspace = "default"
        self._sleep_seconds = float(sleep_seconds)
        self.events: list[tuple[str, str, float]] = []
        self._lock = threading.Lock()

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": "context_get", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "diary", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "profile", "parameters": {"type": "object"}}},
        ]

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        start = time.perf_counter()
        with self._lock:
            self.events.append(("start", str(name), start))
        time.sleep(self._sleep_seconds)
        end = time.perf_counter()
        with self._lock:
            self.events.append(("end", str(name), end))
        if str(name) == "profile":
            return {"ok": True, "note_id": 1}
        return {"ok": True, "items": []}


def _fake_service(rounds: list[dict[str, Any]]):
    completions = _FakeCompletions(rounds)
    return SimpleNamespace(
        config=SimpleNamespace(model="fake-model", temperature=0.0),
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        _completions=completions,
    )


def test_agent_loop_parallel_reads_and_serial_write():
    rounds = [
        {
            "tool_calls": [
                {"id": "c1", "name": "context_get", "arguments": '{"query":"x"}'},
                {"id": "c2", "name": "diary", "arguments": '{"action":"search","query":"x"}'},
                {"id": "c3", "name": "profile", "arguments": '{"action":"append_note","note":"n"}'},
            ]
        },
        {"content": "ok"},
    ]
    tool_hub = _FakeToolHub(sleep_seconds=0.15)
    loop = AelinAgentLoop(
        service=_fake_service(rounds),
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=4,
            max_tool_calls=8,
            max_write_calls=2,
            allow_write_tools=True,
        ),
        max_rounds=3,
    )

    started = time.perf_counter()
    result = loop.run(query="test", memory_summary="m", history_turns=[])
    elapsed = time.perf_counter() - started

    assert result.ok is True
    assert result.answer == "ok"
    assert len(result.tool_runs) == 3
    assert elapsed < 0.42

    starts = {name: ts for kind, name, ts in tool_hub.events if kind == "start"}
    ends = {name: ts for kind, name, ts in tool_hub.events if kind == "end"}
    assert "context_get" in starts and "diary" in starts and "profile" in starts
    assert starts["profile"] >= max(ends["context_get"], ends["diary"])


def test_agent_loop_rejected_calls_do_not_consume_budget():
    rounds = [
        {
            "tool_calls": [
                {"id": "w1", "name": "profile", "arguments": '{"action":"append_note","note":"n1"}'},
                {"id": "w2", "name": "tracking", "arguments": '{"action":"create","target":"x"}'},
            ]
        },
        {"content": "ok"},
    ]
    tool_hub = _FakeToolHub(sleep_seconds=0.01)
    loop = AelinAgentLoop(
        service=_fake_service(rounds),
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=2,
            max_tool_calls=2,
            max_write_calls=1,
            allow_write_tools=False,
        ),
        max_rounds=3,
    )

    result = loop.run(query="test", memory_summary="m", history_turns=[])

    assert result.ok is True
    assert result.answer == "ok"
    assert result.total_calls == 0
    assert result.write_calls == 0
    assert result.tool_runs
    assert all(run.status == "failed" for run in result.tool_runs)
    # Rejected writes should not execute actual tool handlers.
    assert not tool_hub.events


def test_agent_loop_builds_multimodal_user_message_and_keeps_tool_rounds():
    rounds = [
        {
            "tool_calls": [
                {"id": "c1", "name": "context_get", "arguments": '{"query":"x"}'},
            ]
        },
        {"content": "ok"},
    ]
    service = _fake_service(rounds)
    tool_hub = _FakeToolHub(sleep_seconds=0.01)
    loop = AelinAgentLoop(
        service=service,
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=2,
            max_tool_calls=4,
            max_write_calls=1,
            allow_write_tools=False,
        ),
        max_rounds=3,
    )

    result = loop.run(
        query="请先看图再继续",
        memory_summary="m",
        history_turns=[],
        images=[{"name": "demo.png", "data_url": "data:image/png;base64,AAA"}],
    )

    assert result.ok is True
    assert result.answer == "ok"
    assert len(result.tool_runs) == 1
    assert len(service._completions.calls) >= 2

    first_messages = service._completions.calls[0]["messages"]
    user_msg = first_messages[-1]
    assert user_msg.get("role") == "user"
    user_content = user_msg.get("content")
    assert isinstance(user_content, list)
    assert user_content[0].get("type") == "text"
    assert user_content[0].get("text") == "请先看图再继续"
    image_part = next((it for it in user_content if it.get("type") == "image_url"), None)
    assert image_part is not None
    assert str(((image_part or {}).get("image_url") or {}).get("url") or "").startswith("data:image/png;base64,")


def test_agent_loop_ignores_oversized_image_data_url():
    rounds = [{"content": "ok"}]
    service = _fake_service(rounds)
    tool_hub = _FakeToolHub(sleep_seconds=0.01)
    loop = AelinAgentLoop(
        service=service,
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=1,
            max_tool_calls=1,
            max_write_calls=0,
            allow_write_tools=False,
        ),
        max_rounds=1,
    )

    oversized_data_url = "data:image/png;base64," + ("A" * 3_000_001)
    result = loop.run(
        query="只走文本",
        memory_summary="m",
        history_turns=[],
        images=[{"name": "too-big.png", "data_url": oversized_data_url}],
    )

    assert result.ok is True
    first_messages = service._completions.calls[0]["messages"]
    user_msg = first_messages[-1]
    assert user_msg.get("role") == "user"
    assert user_msg.get("content") == "只走文本"
