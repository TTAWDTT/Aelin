from __future__ import annotations

from app.services.aelin_loop_types import AgentLoopToolRun


def build_actions(
    *,
    runs: list[AgentLoopToolRun],
) -> list[dict[str, str]]:
    _ = runs
    return []
