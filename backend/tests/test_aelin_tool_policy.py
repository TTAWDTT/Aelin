from __future__ import annotations

from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage, classify_tool_call


def test_classify_pinchtab_as_write_tool():
    # pinchtab 会驱动真实浏览器行为，应计入写操作配额。
    assert classify_tool_call("pinchtab", {"action": "click", "tab_id": "t1", "ref": "btn-login"}) is True
    assert classify_tool_call("pinchtab_agent", {"goal": "打开网页并点击登录"}) is True


def test_policy_allows_screen_get_when_reads_enabled():
    policy = AelinToolPolicy(
        max_calls_per_round=2,
        max_tool_calls=4,
        max_write_calls=1,
        allow_write_tools=False,
    )
    decision = policy.evaluate(
        name="screen_get",
        args={"max_edge": 1280},
        usage=ToolPolicyUsage(round_calls=0, total_calls=0, write_calls=0),
    )
    assert decision.allowed is True
    assert decision.is_write is False


def test_policy_blocks_pinchtab_when_writes_disabled():
    policy = AelinToolPolicy(
        max_calls_per_round=2,
        max_tool_calls=4,
        max_write_calls=1,
        allow_write_tools=False,
    )
    decision = policy.evaluate(
        name="pinchtab",
        args={"action": "click", "tab_id": "t1", "ref": "btn-delete"},
        usage=ToolPolicyUsage(round_calls=0, total_calls=0, write_calls=0),
    )
    assert decision.allowed is False
    assert decision.is_write is True
    assert decision.reason == "write_tools_disabled"

    decision_agent = policy.evaluate(
        name="pinchtab_agent",
        args={"goal": "尝试在网页上执行操作"},
        usage=ToolPolicyUsage(round_calls=0, total_calls=0, write_calls=0),
    )
    assert decision_agent.allowed is False
    assert decision_agent.is_write is True
    assert decision_agent.reason == "write_tools_disabled"
