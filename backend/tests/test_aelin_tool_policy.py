from __future__ import annotations

from app.services.deepagents.tool_runtime import ToolCallLimiter, ToolPolicyUsage, classify_tool_call


def test_classify_write_tools():
    # 仅 device / google_workspace 视为写操作，其余工具全部为只读。
    assert classify_tool_call("device", {"action": "status"}) is False
    assert classify_tool_call("device", {"action": "open_url", "url": "https://example.com"}) is True
    assert classify_tool_call("device", {"action": "open_aelin", "route": "/"}) is True


def test_policy_allows_screen_get_when_reads_enabled():
    policy = ToolCallLimiter(
        max_tool_calls=4,
        max_write_calls=1,
        allow_write_tools=False,
    )
    decision = policy.evaluate(
        name="screen_get",
        args={"max_edge": 1280},
        usage=ToolPolicyUsage(total_calls=0, write_calls=0),
    )
    assert decision.allowed is True
    assert decision.is_write is False

        # 旧版 skill 工具已移除，不再属于受支持的工具集合。


def test_policy_blocks_device_writes_when_writes_disabled():
    policy = ToolCallLimiter(
        max_tool_calls=4,
        max_write_calls=1,
        allow_write_tools=False,
    )
    decision = policy.evaluate(
        name="device",
        args={"action": "open_url", "url": "https://example.com"},
        usage=ToolPolicyUsage(total_calls=0, write_calls=0),
    )
    assert decision.allowed is False
    assert decision.is_write is True
    assert decision.reason == "write_tools_disabled"


def test_classify_device_actions():
    assert classify_tool_call("device", {"action": "status"}) is False
    assert classify_tool_call("device", {"action": "open_url", "url": "https://example.com"}) is True
    assert classify_tool_call("device", {"action": "open_aelin", "route": "/"}) is True


def test_google_workspace_policy_allows_reads_and_marks_writes():
    usage = ToolPolicyUsage(total_calls=0, write_calls=0)
    policy = ToolCallLimiter(
        max_tool_calls=10,
        max_write_calls=3,
        allow_write_tools=True,
    )

    # 读操作：不计入写配额，默认允许。
    read_decision = policy.evaluate(
        name="google_workspace",
        args={"action": "gmail_list", "query": "is:unread"},
        usage=usage,
    )
    assert read_decision.allowed is True
    assert read_decision.is_write is False

    # 写操作：标记为写，且在允许写工具时仍然放行，由上层根据配额限制。
    write_decision = policy.evaluate(
        name="google_workspace",
        args={"action": "calendar_create_event"},
        usage=usage,
    )
    assert write_decision.allowed is True
    assert write_decision.is_write is True

