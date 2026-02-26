from __future__ import annotations

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

    def create(self, **kwargs):
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

