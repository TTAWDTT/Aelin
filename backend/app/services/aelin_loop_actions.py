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
        result = run.result if isinstance(run.result, dict) else {}
        if run.status != "completed":
            continue
        if run.name == "diary":
            items = result.get("items") if isinstance(result.get("items"), list) else []
            first = items[0] if items and isinstance(items[0], dict) else {}
            path = str(first.get("path") or "").strip()[:220]
            if path:
                out.append(
                    {
                        "kind": "open_desk",
                        "title": "查看日记命中",
                        "detail": path,
                        "path": path,
                        "workspace": str(workspace),
                    }
                )
        if len(out) >= 4:
            break
    return out
