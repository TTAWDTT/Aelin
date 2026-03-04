from __future__ import annotations

from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage, classify_tool_call


def test_classify_browser_tools():
    assert classify_tool_call("browser_state_get", {}) is False
    assert classify_tool_call("browser_session_list", {}) is False
    assert classify_tool_call("browser_use", {"action": "click"}) is True


def test_policy_allows_browser_state_get_when_reads_enabled():
    policy = AelinToolPolicy(
        max_calls_per_round=2,
        max_tool_calls=4,
        max_write_calls=1,
        allow_write_tools=False,
    )
    decision = policy.evaluate(
        name="browser_state_get",
        args={"include_dom": True},
        usage=ToolPolicyUsage(round_calls=0, total_calls=0, write_calls=0),
    )
    assert decision.allowed is True
    assert decision.is_write is False


def test_policy_allows_browser_session_list_when_reads_enabled():
    policy = AelinToolPolicy(
        max_calls_per_round=2,
        max_tool_calls=4,
        max_write_calls=1,
        allow_write_tools=False,
    )
    decision = policy.evaluate(
        name="browser_session_list",
        args={"scope": "all"},
        usage=ToolPolicyUsage(round_calls=0, total_calls=0, write_calls=0),
    )
    assert decision.allowed is True
    assert decision.is_write is False


def test_policy_blocks_browser_use_when_writes_disabled():
    policy = AelinToolPolicy(
        max_calls_per_round=2,
        max_tool_calls=4,
        max_write_calls=1,
        allow_write_tools=False,
    )
    decision = policy.evaluate(
        name="browser_use",
        args={"action": "click", "target": "Delete"},
        usage=ToolPolicyUsage(round_calls=0, total_calls=0, write_calls=0),
    )
    assert decision.allowed is False
    assert decision.is_write is True
    assert decision.reason == "write_tools_disabled"
