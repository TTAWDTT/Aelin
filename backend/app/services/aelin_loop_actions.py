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
        if run.name == "tracking" and int(result.get("target_id") or 0) > 0:
            target_id = int(result.get("target_id") or 0)
            out.append(
                {
                    "kind": "open_tracking",
                    "title": "已创建追踪",
                    "detail": str(result.get("target") or f"target_id={target_id}")[:120],
                    "target_id": str(target_id),
                    "workspace": str(workspace),
                }
            )
        if run.name == "diary":
            items = result.get("items") if isinstance(result.get("items"), list) else []
            first = items[0] if items and isinstance(items[0], dict) else {}
            path = str(first.get("path") or "").strip()[:220]
            if path:
                out.append(
                    {
                        "kind": "open_tracking",
                        "title": "查看日记命中",
                        "detail": path,
                        "path": path,
                        "workspace": str(workspace),
                    }
                )
        if len(out) >= 4:
            break
    return out
