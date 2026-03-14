from __future__ import annotations

from app.services.aelin_loop_types import AgentLoopToolRun


def build_actions(
    *,
    runs: list[AgentLoopToolRun],
    user_id: int,
    workspace: str,
    resume_query: str = "",
    resume_request_json: str = "",
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for run in runs:
        if run.status != "completed":
            continue
        if len(out) >= 4:
            break
    return out
