from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.services.deepagents.deepagents_graph import DeepAgentsLoopResult


class _FakeToolContext:
    """
    Minimal stand-in for ToolRuntimeContext used in DeepAgents-related tests.

    It only records constructor kwargs and exposes `workspace` / `user_id`
    attributes so tests can assert that the runtime context is wired correctly.
    """

    instances: list["_FakeToolContext"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.workspace = str(kwargs.get("workspace") or "default")
        self.user_id = int(kwargs.get("user_id") or 0)
        _FakeToolContext.instances.append(self)


class _FakeRunner:
    """
    Simple callable fake used to capture DeepAgents `invoke_payload` calls.
    """

    calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        # Mirror the DeepAgents bridge constructor surface without depending
        # on the actual implementation, so this fake can be injected via
        # monkeypatch in tests.
        self.kwargs = kwargs

    def __call__(self, invoke_payload: Any) -> SimpleNamespace:
        # DeepAgents agent is invoked as a callable with {"messages": ...}
        # and optional "files" mapping; record the payload for assertions.
        _FakeRunner.calls.append(dict(invoke_payload))
        return SimpleNamespace(content="ok")


def _reset_fakes() -> None:
    """
    Clear all state accumulated in shared DeepAgents test fakes.
    """
    _FakeToolContext.instances.clear()
    _FakeRunner.calls.clear()


def make_loop_result(
    *,
    ok: bool = True,
    answer: str = "ok",
    total_calls: int = 0,
    write_calls: int = 0,
    tool_runs: list[dict[str, Any]] | None = None,
    actions: list[dict[str, str]] | None = None,
    error: str = "",
) -> DeepAgentsLoopResult:
    """
    Convenience helper for constructing DeepAgentsLoopResult values in tests.

    This keeps boilerplate consistent across DeepAgents bridge tests while
    allowing individual tests to override only the fields that matter for
    their assertions.
    """
    return DeepAgentsLoopResult(
        ok=ok,
        answer=answer,
        tool_runs=tool_runs or [],
        total_calls=total_calls,
        write_calls=write_calls,
        actions=actions or [],
        error=error,
    )
