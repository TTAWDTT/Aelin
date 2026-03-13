from __future__ import annotations

import copy
import json
import threading
import time
from types import SimpleNamespace
from typing import Any

from app.services import aelin_agent_loop as aelin_agent_loop_module
from app.services.aelin_agent_loop import AelinAgentLoop
from app.services.aelin_loop_tools import (
    _compact_tool_result_for_model,
    _sanitize_for_log,
    _serialize_tool_message_content,
)
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
        if row.get("raise"):
            raise RuntimeError(str(row.get("raise")))
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
            {"type": "function", "function": {"name": "screen_get", "parameters": {"type": "object"}}},
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
        if str(name) == "screen_get":
            return {"ok": True, "data_url": "data:image/png;base64,AAA", "width": 800, "height": 600}
        return {"ok": True, "items": []}


class _CaptureBrowserToolHub(_FakeToolHub):
    def __init__(self) -> None:
        super().__init__(sleep_seconds=0.0)


class _FakePlaneToolHub(_FakeToolHub):
    def __init__(self) -> None:
        super().__init__(sleep_seconds=0.0)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._status_count = 0

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": "plane", "parameters": {"type": "object"}}},
        ]

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((str(name), dict(args)))
        if str(name) != "plane":
            return {"ok": False, "error": "unsupported"}
        action = str(args.get("action") or "").strip().lower()
        if action == "delegate":
            return {
                "ok": True,
                "plane": "browser",
                "task_id": "browser-task-1",
                "state": "running",
                "summary": "browser task running",
                "last_url": "https://example.com",
            }
        if action == "status":
            self._status_count += 1
            return {
                "ok": True,
                "plane": "browser",
                "task_id": "browser-task-1",
                "state": "completed" if self._status_count >= 1 else "running",
                "summary": "browser task completed",
                "last_url": "https://example.com/final",
                "last_text": "final page text",
            }
        if action == "continue":
            return {
                "ok": True,
                "plane": "browser",
                "task_id": "browser-task-1",
                "state": "completed",
                "summary": "browser task completed after continue",
                "last_url": "https://example.com/continued",
                "last_text": "continued page text",
            }
        return {"ok": False, "error": f"unsupported:{action}"}


class _FakeWaitingPlaneToolHub(_FakeToolHub):
    def __init__(self) -> None:
        super().__init__(sleep_seconds=0.0)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": "plane", "parameters": {"type": "object"}}},
        ]

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((str(name), dict(args)))
        if str(name) != "plane":
            return {"ok": False, "error": "unsupported"}
        action = str(args.get("action") or "").strip().lower()
        if action == "delegate":
            return {
                "ok": True,
                "plane": "browser",
                "task_id": "browser-task-waiting",
                "state": "waiting_user",
                "summary": "waiting for login",
                "user_prompt": "请先完成登录",
                "requires_user_input": True,
                "last_url": "https://x.com/i/flow/login",
            }
        if action == "status":
            return {
                "ok": True,
                "plane": "browser",
                "task_id": "browser-task-waiting",
                "state": "completed",
                "summary": "login completed",
                "last_url": "https://x.com/home",
                "last_text": "home page",
            }
        return {"ok": False, "error": f"unsupported:{action}"}


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
                {"id": "w2", "name": "pinchtab", "arguments": '{"action":"click","tab_id":"t1","ref":"btn"}'},
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


def test_agent_loop_retries_with_text_only_when_multimodal_unsupported():
    rounds = [
        {"raise": "This model does not support image_url content"},
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
            max_tool_calls=2,
            max_write_calls=1,
            allow_write_tools=False,
        ),
        max_rounds=2,
    )

    result = loop.run(
        query="请看图并继续",
        memory_summary="m",
        history_turns=[],
        images=[{"name": "demo.png", "data_url": "data:image/png;base64,AAA"}],
    )

    assert result.ok is True
    assert result.answer == "ok"
    assert len(service._completions.calls) >= 2

    first_messages = service._completions.calls[0]["messages"]
    second_messages = service._completions.calls[1]["messages"]
    first_user = first_messages[-1]
    second_user = second_messages[-1]
    assert first_user.get("role") == "user"
    assert isinstance(first_user.get("content"), list)
    assert second_user.get("role") == "user"
    assert second_user.get("content") == "请看图并继续"


def test_agent_loop_injects_tool_screen_image_for_next_round():
    rounds = [
        {
            "tool_calls": [
                {"id": "s1", "name": "screen_get", "arguments": "{}"},
            ]
        },
        {"content": "看到了"},
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
            max_write_calls=0,
            allow_write_tools=False,
        ),
        max_rounds=2,
    )

    result = loop.run(query="看看屏幕", memory_summary="m", history_turns=[])

    assert result.ok is True
    assert result.answer == "看到了"
    assert len(service._completions.calls) >= 2

    second_messages = service._completions.calls[1]["messages"]
    screen_msgs = [
        row
        for row in second_messages
        if row.get("role") == "user"
        and isinstance(row.get("content"), list)
        and any(str(item.get("type") or "") == "image_url" for item in row.get("content") if isinstance(item, dict))
    ]
    assert screen_msgs


def test_build_resume_request_payload_summarizes_images():
    payload = aelin_agent_loop_module._build_resume_request_payload(
        query="继续处理",
        workspace="default",
        history_turns=[{"role": "user", "content": "上一轮"}],
        images=[{"data_url": "data:image/png;base64,QUFBQQ==", "name": "following.png"}],
        attachment_ids=[7, 0, 9],
    )

    assert payload["images"] == []
    assert payload["history"] == [{"role": "user", "content": "上一轮"}]
    assert payload["attachment_ids"] == [7, 9]
    summaries = payload.get("image_summaries") if isinstance(payload.get("image_summaries"), list) else []
    assert summaries
    assert str(summaries[0].get("name") or "") == "following.png"
    assert str(summaries[0].get("mime_type") or "") == "image/png"
    assert int(summaries[0].get("byte_length") or 0) > 0


def test_serialize_tool_message_content_keeps_valid_json_when_truncated():
    payload = {"ok": True, "data": "x" * 20000}
    content = _serialize_tool_message_content(payload, max_len=8000)
    parsed = json.loads(content)
    assert isinstance(parsed, dict)
    assert parsed.get("truncated") is True
    assert int(parsed.get("original_length") or 0) > 8000


def test_sanitize_for_log_redacts_sensitive_keys():
    payload = {
        "value": "super-secret-password",
        "password": "p@ss",
        "headers": {"Authorization": "Bearer abc", "X-Api-Key": "xyz"},
        "normal": "hello",
    }
    safe = _sanitize_for_log(payload)
    assert isinstance(safe, dict)
    assert str(safe.get("value") or "").startswith("<redacted")
    assert str(safe.get("password") or "").startswith("<redacted")
    headers = safe.get("headers")
    assert isinstance(headers, dict)
    assert str(headers.get("Authorization") or "").startswith("<redacted")
    assert str(headers.get("X-Api-Key") or "").startswith("<redacted")
    assert safe.get("normal") == "hello"


def test_sanitize_tool_args_for_log_masks_browser_type_inputs():
    raw_args = {
        "action": "type",
        "scope": "managed",
        "strategy": "selector",
        "target": "#password",
        "value": "my-secret",
        "confirm": True,
    }
    safe = _sanitize_for_log(raw_args)
    assert isinstance(safe, dict)
    assert str(safe.get("value") or "").startswith("<redacted")
    assert safe.get("scope") == "managed"


def test_compact_tool_result_for_model_preserves_pinchtab_ids():
    # PinchTab results must keep instance_id / tab_id so the model can chain calls.
    result1 = _compact_tool_result_for_model("pinchtab", {"ok": True, "instance_id": "inst_123"})
    assert result1.get("ok") is True
    assert result1.get("instance_id") == "inst_123"

    result2 = _compact_tool_result_for_model("pinchtab", {"ok": True, "tab_id": "tab_456"})
    assert result2.get("ok") is True
    assert result2.get("tab_id") == "tab_456"


def test_compact_tool_result_for_model_preserves_plane_ids():
    result = _compact_tool_result_for_model(
        "plane",
        {"ok": True, "plane": "browser", "task_id": "task_123", "state": "running", "last_url": "https://x.com"},
    )
    assert result.get("ok") is True
    assert result.get("plane") == "browser"
    assert result.get("task_id") == "task_123"
    assert result.get("state") == "running"


def test_agent_loop_keeps_supervising_active_plane_before_accepting_final_answer():
    rounds = [
        {
            "tool_calls": [
                {"id": "p1", "name": "plane", "arguments": '{"action":"delegate","plane":"browser","goal":"总结 example 页面"}'},
            ]
        },
        {"content": "我先直接总结。"},
        {"content": "最终结果"},
    ]
    service = _fake_service(rounds)
    tool_hub = _FakePlaneToolHub()
    loop = AelinAgentLoop(
        service=service,
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=2,
            max_tool_calls=4,
            max_write_calls=2,
            allow_write_tools=True,
        ),
        max_rounds=4,
    )

    result = loop.run(query="总结 example 页面", memory_summary="m", history_turns=[])

    assert result.ok is True
    assert result.answer == "最终结果"
    assert result.total_calls == 2
    assert [call[1].get("action") for call in tool_hub.calls] == ["delegate", "status"]
    assert len(service._completions.calls) == 3
    assert any(run.name == "plane" and str(run.result.get("state") or "") == "completed" for run in result.tool_runs)


def test_agent_loop_prioritizes_existing_active_plane_task_before_finalizing():
    rounds = [
        {"content": "我直接回答。"},
        {"content": "真正最终结果"},
    ]
    service = _fake_service(rounds)
    tool_hub = _FakePlaneToolHub()
    loop = AelinAgentLoop(
        service=service,
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=2,
            max_tool_calls=4,
            max_write_calls=2,
            allow_write_tools=True,
        ),
        max_rounds=3,
    )

    result = loop.run(
        query="继续总结这个网页任务",
        memory_summary="m",
        history_turns=[],
        forced_tool_runs=[
            {
                "name": "plane",
                "args": {"action": "status", "plane": "browser", "task_id": "browser-task-1"},
                "result": {
                    "ok": True,
                    "plane": "browser",
                    "task_id": "browser-task-1",
                    "state": "running",
                    "summary": "browser task running",
                    "last_url": "https://example.com",
                },
            }
        ],
    )

    assert result.ok is True
    assert result.answer == "真正最终结果"
    assert result.total_calls == 1
    assert [call[1].get("action") for call in tool_hub.calls] == ["status"]
    assert len(service._completions.calls) == 2


def test_agent_loop_allows_continue_on_supervised_plane_task_before_terminal_answer():
    rounds = [
        {
            "tool_calls": [
                {"id": "p1", "name": "plane", "arguments": '{"action":"delegate","plane":"browser","goal":"进入后台页面"}'},
            ]
        },
        {
            "tool_calls": [
                {"id": "p2", "name": "plane", "arguments": '{"action":"continue","plane":"browser","task_id":"browser-task-1","goal":"继续读取详情"}'},
            ]
        },
        {"content": "继续后的最终结果"},
    ]
    service = _fake_service(rounds)
    tool_hub = _FakePlaneToolHub()
    loop = AelinAgentLoop(
        service=service,
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=2,
            max_tool_calls=4,
            max_write_calls=3,
            allow_write_tools=True,
        ),
        max_rounds=4,
    )

    result = loop.run(query="进入后台页面并继续读取详情", memory_summary="m", history_turns=[])

    assert result.ok is True
    assert result.answer == "继续后的最终结果"
    assert result.total_calls == 2
    assert [call[1].get("action") for call in tool_hub.calls] == ["delegate", "continue"]


def test_agent_loop_stops_with_user_prompt_when_plane_enters_waiting_user():
    rounds = [
        {
            "tool_calls": [
                {"id": "p1", "name": "plane", "arguments": '{"action":"delegate","plane":"browser","goal":"登录 X 后继续"}'},
            ]
        },
        {"content": "我先自己总结。"},
    ]
    service = _fake_service(rounds)
    tool_hub = _FakeWaitingPlaneToolHub()
    loop = AelinAgentLoop(
        service=service,
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=2,
            max_tool_calls=4,
            max_write_calls=2,
            allow_write_tools=True,
        ),
        max_rounds=3,
    )

    result = loop.run(query="登录 X 后继续", memory_summary="m", history_turns=[])

    assert result.ok is True
    assert result.answer == "请先完成登录"
    assert result.stop_reason == "plane_waiting_user"
    assert [call[1].get("action") for call in tool_hub.calls] == ["delegate"]


def test_agent_loop_resumes_waiting_plane_with_status_probe_on_next_user_turn():
    rounds = [
        {"content": "我已经登录好了"},
        {"content": "恢复后的最终结果"},
    ]
    service = _fake_service(rounds)
    tool_hub = _FakeWaitingPlaneToolHub()
    loop = AelinAgentLoop(
        service=service,
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=2,
            max_tool_calls=4,
            max_write_calls=2,
            allow_write_tools=True,
        ),
        max_rounds=3,
    )

    result = loop.run(
        query="我已经登录好了",
        memory_summary="m",
        history_turns=[],
        forced_tool_runs=[
            {
                "name": "plane",
                "args": {"action": "status", "plane": "browser", "task_id": "browser-task-waiting"},
                "result": {
                    "ok": True,
                    "plane": "browser",
                    "task_id": "browser-task-waiting",
                    "state": "waiting_user",
                    "summary": "waiting for login",
                    "user_prompt": "请先完成登录",
                    "requires_user_input": True,
                    "last_url": "https://x.com/i/flow/login",
                },
            }
        ],
    )

    assert result.ok is True
    assert result.answer == "恢复后的最终结果"
    assert result.total_calls == 1
    assert [call[1].get("action") for call in tool_hub.calls] == ["status"]
