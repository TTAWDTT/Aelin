from __future__ import annotations

import copy
import json
import threading
import time
from types import SimpleNamespace
from typing import Any

from app.services.aelin_agent_loop import AelinAgentLoop
from app.services.aelin_loop_tools import _sanitize_for_log, _sanitize_tool_args_for_log, _serialize_tool_message_content
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
            {"type": "function", "function": {"name": "browser_state_get", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "browser_use", "parameters": {"type": "object"}}},
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
        if str(name) == "browser_state_get":
            return {"ok": True, "url": "about:blank", "title": "", "session_scope": "agent_browser", "is_blank_page": True}
        if str(name) == "browser_use":
            return {"ok": True, "action": str(args.get("action") or ""), "scope": "cdp"}
        return {"ok": True, "items": []}


class _ConfirmToolHub(_FakeToolHub):
    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if str(name) == "browser_use":
            return {
                "ok": False,
                "error": "browser_restart_confirmation_required",
                "requires_confirmation": True,
                "confirm_kind": "restart_to_cdp",
                "action": str(args.get("action") or "click"),
                "user_prompt": "该任务较为复杂，需要重启浏览器后才能执行，是否确认？",
                "next_call": {
                    "tool": "browser_use",
                    "action": "click",
                    "args": {"target": "关注", "scope": "cdp", "confirm": True},
                },
            }
        return super().execute(name, args)


class _StateConfirmToolHub(_FakeToolHub):
    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if str(name) == "browser_state_get":
            return {
                "ok": False,
                "error": "browser_restart_confirmation_required",
                "requires_confirmation": True,
                "confirm_kind": "restart_to_cdp",
                "action": "state_get",
                "user_prompt": "读取页面内容需要切换到 CDP 并重启浏览器，是否确认？",
                "next_call": {
                    "tool": "browser_state_get",
                    "action": "state_get",
                    "args": {"scope": "cdp", "include_dom": True, "include_a11y": False, "max_targets": 30},
                },
            }
        return super().execute(name, args)


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


def test_agent_loop_browser_state_get_is_serialized_from_parallel_read_batch():
    rounds = [
        {
            "tool_calls": [
                {"id": "c1", "name": "context_get", "arguments": '{"query":"x"}'},
                {"id": "b1", "name": "browser_state_get", "arguments": '{"include_dom":true}'},
            ]
        },
        {"content": "ok"},
    ]
    tool_hub = _FakeToolHub(sleep_seconds=0.12)
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

    result = loop.run(query="test", memory_summary="m", history_turns=[])
    assert result.ok is True
    assert result.answer == "ok"

    starts = {name: ts for kind, name, ts in tool_hub.events if kind == "start"}
    ends = {name: ts for kind, name, ts in tool_hub.events if kind == "end"}
    assert "context_get" in starts and "browser_state_get" in starts
    assert starts["browser_state_get"] >= ends["context_get"]


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


def test_agent_loop_stops_with_confirmation_when_browser_use_requires_it():
    rounds = [
        {
            "tool_calls": [
                {"id": "b1", "name": "browser_use", "arguments": '{"action":"click","target":"关注","scope":"auto"}'},
            ]
        },
        {"content": "不应到达"},
    ]
    service = _fake_service(rounds)
    tool_hub = _ConfirmToolHub(sleep_seconds=0.01)
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
        max_rounds=2,
    )

    result = loop.run(query="帮我打开并读取关注列表", memory_summary="m", history_turns=[])
    assert result.ok is True
    assert result.stop_reason == "requires_confirmation"
    assert "是否确认" in result.answer
    assert len(service._completions.calls) == 1
    confirm_actions = [action for action in result.actions if str(action.get("kind") or "") == "confirm_browser_action"]
    assert confirm_actions
    assert str(confirm_actions[0].get("resume_query") or "") == "帮我打开并读取关注列表"
    next_call = json.loads(str(confirm_actions[0].get("next_call") or "{}"))
    assert str(next_call.get("tool") or "") == "browser_use"
    next_args = next_call.get("args") if isinstance(next_call.get("args"), dict) else {}
    assert str(next_args.get("scope") or "") == "cdp"
    assert bool(next_args.get("confirm")) is True


def test_agent_loop_stops_with_confirmation_when_browser_state_get_requires_it():
    rounds = [
        {
            "tool_calls": [
                {"id": "s1", "name": "browser_state_get", "arguments": '{"scope":"auto","include_dom":true}'},
            ]
        },
        {"content": "不应到达"},
    ]
    service = _fake_service(rounds)
    tool_hub = _StateConfirmToolHub(sleep_seconds=0.01)
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
        max_rounds=2,
    )

    result = loop.run(query="读取当前页面并总结", memory_summary="m", history_turns=[])
    assert result.ok is True
    assert result.stop_reason == "requires_confirmation"
    assert "是否确认" in result.answer
    assert len(service._completions.calls) == 1
    confirm_actions = [action for action in result.actions if str(action.get("kind") or "") == "confirm_browser_action"]
    assert confirm_actions
    next_call = json.loads(str(confirm_actions[0].get("next_call") or "{}"))
    assert str(next_call.get("tool") or "") == "browser_state_get"
    assert str(next_call.get("action") or "") == "state_get"
    next_args = next_call.get("args") if isinstance(next_call.get("args"), dict) else {}
    assert str(next_args.get("scope") or "") == "cdp"
    assert bool(next_args.get("include_dom")) is True


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
    safe = _sanitize_tool_args_for_log("browser_use", raw_args)
    assert isinstance(safe, dict)
    assert safe.get("action") == "type"
    assert safe.get("scope") == "managed"
    assert safe.get("sensitive_args") is True
    assert "value" not in safe
    assert "target" not in safe
