from __future__ import annotations

from types import SimpleNamespace

from app.services.deepagents.deepagents_graph import _build_system_prompt
from app.services.deepagents.model_timeout_middleware import (
    DeepAgentsToolAvailabilityMiddleware,
)


def test_build_system_prompt_only_mentions_execute_when_available() -> None:
    prompt_without_execute = _build_system_prompt(["web_search", "attachment_search"])
    prompt_with_execute = _build_system_prompt(["web_search", "execute"])

    assert "- execute:" not in prompt_without_execute
    assert "- execute:" in prompt_with_execute
    assert "- web_search:" in prompt_without_execute
    assert "- attachment_search:" in prompt_without_execute


def test_build_system_prompt_guides_execute_for_windows_shell_usage() -> None:
    prompt = _build_system_prompt(["execute"])

    assert "windows" in prompt.lower()
    assert "cwd" in prompt
    assert "mkdir -p" in prompt
    assert "relative path" in prompt.lower() or "relative paths" in prompt.lower()
    assert "do not prepend cd" in prompt.lower()


def test_build_system_prompt_omits_empty_tool_specific_block() -> None:
    prompt = _build_system_prompt([])

    assert "Tool-specific rules:" not in prompt
    assert "You are Aelin running on DeepAgents." in prompt
    assert "Treat /memory/AGENTS.md as the canonical long-term memory file." in prompt


class _FakeRequest:
    def __init__(self, *, tools, system_message: str = "") -> None:
        self.tools = list(tools)
        self.system_message = system_message

    def override(self, **kwargs):  # noqa: ANN003
        cloned = _FakeRequest(
            tools=list(kwargs.get("tools", self.tools)),
            system_message=str(kwargs.get("system_message", self.system_message) or ""),
        )
        for key, value in kwargs.items():
            setattr(cloned, key, value)
        return cloned


def test_tool_availability_middleware_restores_filtered_execute_tool() -> None:
    preserved_execute = SimpleNamespace(name="execute")
    middleware = DeepAgentsToolAvailabilityMiddleware(
        preserved_tools=[preserved_execute]
    )
    captured: dict[str, object] = {}

    def _handler(request):  # noqa: ANN001
        captured["request"] = request
        return "ok"

    result = middleware.wrap_model_call(
        _FakeRequest(
            tools=[SimpleNamespace(name="ls"), SimpleNamespace(name="read_file")],
            system_message="base system message",
        ),
        _handler,
    )

    assert result == "ok"
    request = captured["request"]
    tool_names = [getattr(tool, "name", "") for tool in request.tools]
    assert tool_names == ["ls", "read_file", "execute"]
    assert "Runtime note:" in str(request.system_message)
    assert "do not claim these tools are unavailable" in str(request.system_message).lower()
