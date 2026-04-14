from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.deepagents.deepagents_graph import _build_system_prompt
from app.services.deepagents.model_timeout_middleware import (
    DeepAgentsToolAvailabilityMiddleware,
)


def test_build_system_prompt_only_mentions_execute_when_available() -> None:
    prompt_without_execute = _build_system_prompt(
        ["web_search", "attachment_search"],
        user_id=1,
        workspace="default",
    )
    prompt_with_execute = _build_system_prompt(
        ["web_search", "execute"],
        user_id=1,
        workspace="default",
    )

    assert "- execute:" not in prompt_without_execute
    assert "- execute:" in prompt_with_execute
    assert "- web_search:" in prompt_without_execute
    assert "- attachment_search:" in prompt_without_execute


def test_build_system_prompt_mentions_present_files_contract_when_available() -> None:
    prompt = _build_system_prompt(["present_files"], user_id=1, workspace="default")

    assert "- present_files:" in prompt
    assert "final deliverables must be placed under" in prompt
    assert "/outputs" in prompt
    assert "UI can render cards" in prompt


def test_build_system_prompt_guides_execute_for_windows_shell_usage() -> None:
    prompt = _build_system_prompt(["execute"], user_id=1, workspace="default")

    assert "windows" in prompt.lower()
    assert "cwd" in prompt
    assert "shell='powershell'" in prompt.lower()
    assert "mkdir -p" in prompt
    assert "/workspace" in prompt
    assert "/outputs" in prompt
    assert "do not prepend cd" in prompt.lower()


def test_build_system_prompt_omits_empty_tool_specific_block() -> None:
    prompt = _build_system_prompt([], user_id=1, workspace="default")

    assert "Tool-specific rules:" not in prompt
    assert "You are Aelin running on DeepAgents." in prompt
    assert "Treat /memory/AGENTS.md as the compact runtime memory projection for this run." in prompt


def test_canvas_design_skill_frontmatter_uses_generic_delivery_contract() -> None:
    skill_path = (
        Path(__file__).resolve().parents[1]
        / "deepagents_skills"
        / "anthropic-canvas-design"
        / "SKILL.md"
    )
    skill_text = skill_path.read_text(encoding="utf-8")

    assert "allowed-tools: execute write_file edit_file read_file glob present_files" in skill_text
    assert "Create source files" in skill_text
    assert "/workspace" in skill_text
    assert "/outputs" in skill_text
    assert "present_files" in skill_text


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
    preserved_present = SimpleNamespace(name="present_files")
    middleware = DeepAgentsToolAvailabilityMiddleware(
        preserved_tools=[preserved_execute, preserved_present]
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
    assert tool_names == ["ls", "read_file", "execute", "present_files"]
    assert "Runtime note:" in str(request.system_message)
    assert "do not claim these tools are unavailable" in str(request.system_message).lower()
    assert "present_files" in str(request.system_message)
