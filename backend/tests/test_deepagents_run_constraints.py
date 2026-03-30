from __future__ import annotations

from app.services.deepagents.tool_runtime import (
    ToolCallLimiter,
    ToolPolicyUsage,
    build_tool_signature,
    result_has_progress,
)
from app.services.tools.tools_gws import tool_google_workspace
from app.services.tools.tools_web import tool_web_search


def test_tool_call_limiter_blocks_duplicate_web_search_calls():
    usage = ToolPolicyUsage()
    limiter = ToolCallLimiter(
        max_tool_calls=10,
        max_write_calls=2,
        allow_write_tools=True,
        consecutive_failures_limit=3,
        consecutive_no_progress_limit=2,
    )
    args = {"action": "search_and_fetch", "query": "github trending today"}

    first = limiter.evaluate(name="web_search", args=args, usage=usage)
    assert first.allowed is True
    usage.note_invocation("web_search", args)

    second = limiter.evaluate(name="web_search", args=args, usage=usage)
    assert second.allowed is False
    assert "duplicate_web_search_call" in second.reason


def test_web_search_signature_keeps_distinct_queries_distinct():
    left = build_tool_signature(
        "web_search",
        {"action": "search_and_fetch", "query": "GitHub trending today 2026-03-26 top projects"},
    )
    right = build_tool_signature(
        "web_search",
        {"action": "search_and_fetch", "query": "\"GitHub trending\" \"today\" \"2026-03-26\" repositories stars"},
    )

    assert left != right


def test_tool_web_search_requires_real_fetch_for_search_and_fetch():
    result = tool_web_search(
        context=type("Ctx", (), {"web_search_service": None})(),
        args={"action": "search_and_fetch", "query": "nba standings", "fetch_top_k": 0},
    )
    assert result["ok"] is False
    assert "invalid search_and_fetch call" in str(result["error"])


def test_tool_call_limiter_allows_corrected_web_search_after_invalid_attempt():
    usage = ToolPolicyUsage()
    limiter = ToolCallLimiter(
        max_tool_calls=10,
        max_write_calls=2,
        allow_write_tools=True,
        consecutive_failures_limit=3,
        consecutive_no_progress_limit=2,
    )

    invalid = limiter.evaluate(name="web_search", args={"action": "search_and_fetch", "query": ""}, usage=usage)
    assert invalid.allowed is False
    assert "non-empty query" in invalid.reason

    usage.note_denial()

    corrected = limiter.evaluate(
        name="web_search",
        args={"action": "search_and_fetch", "query": "github trending today", "fetch_top_k": 2},
        usage=usage,
    )
    assert corrected.allowed is True


def test_tool_google_workspace_validates_required_write_fields(monkeypatch):
    class _FakeService:
        def runtime_status(self):
            return {"available": True}

        def auth_status(self):
            return {"authenticated": True}

    monkeypatch.setattr(
        "app.services.tools.tools_gws.get_google_workspace_cli_service",
        lambda: _FakeService(),
    )

    result = tool_google_workspace(None, {"action": "gmail_send", "email_to": ["a@example.com"]})
    assert result["ok"] is False
    assert "requires email_subject" in str(result["error"])


def test_tool_google_workspace_stops_when_auth_missing(monkeypatch):
    class _FakeService:
        def runtime_status(self):
            return {"available": True}

        def auth_status(self):
            return {
                "authenticated": False,
                "login_command": ["gws", "auth", "login"],
                "email": "",
            }

        def login_command(self):
            return ["gws", "auth", "login"]

    monkeypatch.setattr(
        "app.services.tools.tools_gws.get_google_workspace_cli_service",
        lambda: _FakeService(),
    )

    result = tool_google_workspace(None, {"action": "gmail_get", "message_id": "123"})
    assert result["ok"] is False
    assert result["stop_retry"] is True
    assert "authorization required" in str(result["error"])


def test_result_has_progress_treats_artifacts_as_progress():
    assert result_has_progress(
        {
            "ok": True,
            "artifacts": [
                {"path": "D:/Github/Aelin/output/poster.png"},
            ],
        }
    ) is True


def test_result_has_progress_treats_failed_execute_with_stderr_as_progress():
    assert result_has_progress(
        {
            "ok": False,
            "summary": "command failed with exit code 1",
            "stderr": "The filename, directory name, or volume label syntax is incorrect.",
        }
    ) is True


def test_tool_call_limiter_allows_execute_retry_after_informative_failures():
    usage = ToolPolicyUsage()
    limiter = ToolCallLimiter(
        max_tool_calls=10,
        max_write_calls=10,
        allow_write_tools=True,
        consecutive_failures_limit=3,
        consecutive_no_progress_limit=2,
    )

    first_args = {
        "command": 'cd "D:\\Github\\Aelin\\output\\agent-query-smoke-final-8002" && echo "artifact bridge ok" > smoke.md'
    }
    second_args = {
        "command": 'mkdir -p "D:\\Github\\Aelin\\output\\agent-query-smoke-final-8002" && cd "D:\\Github\\Aelin\\output\\agent-query-smoke-final-8002" && echo "artifact bridge ok" > smoke.md'
    }
    corrected_args = {
        "command": "powershell -Command \"New-Item -ItemType Directory -Force -Path 'D:\\Github\\Aelin\\output\\agent-query-smoke-final-8002'; Set-Content -Path 'D:\\Github\\Aelin\\output\\agent-query-smoke-final-8002\\smoke.md' -Value 'artifact bridge ok'\""
    }

    for args in (first_args, second_args):
        decision = limiter.evaluate(name="execute", args=args, usage=usage)
        assert decision.allowed is True
        usage.note_invocation("execute", args)
        usage.total_calls += 1
        usage.write_calls += 1
        usage.note_result(
            {
                "ok": False,
                "summary": "command failed with exit code 1",
                "stderr": "The filename, directory name, or volume label syntax is incorrect.",
            }
        )

    corrected = limiter.evaluate(name="execute", args=corrected_args, usage=usage)
    assert corrected.allowed is True
