from __future__ import annotations

import json

from app.services.aelin_loop_types import AgentLoopToolRun
from app.services.browser_plane import browser_plane_adapter


def _payload_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:500]
    except Exception:
        return str(value)[:500]


def _payload_json(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{}"


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
        next_call = result.get("next_call") if isinstance(result.get("next_call"), dict) else {}
        next_tool = str(next_call.get("tool") or "").strip().lower()
        should_emit_browser_confirm = bool(result.get("requires_confirmation")) and (
            str(run.name or "").strip().lower() in {"browser_use", "browser_state_get"}
            or next_tool in {"browser_use", "browser_state_get"}
        )
        if run.status != "completed" and should_emit_browser_confirm:
            prompt = str(result.get("user_prompt") or "该任务需要你的确认才能继续执行。").strip()
            login_request_id = _payload_value(result.get("login_request_id"))
            parsed_resume_request: dict[str, object] = {}
            if resume_request_json:
                try:
                    loaded = json.loads(resume_request_json)
                    if isinstance(loaded, dict):
                        parsed_resume_request = dict(loaded)
                except Exception:
                    parsed_resume_request = {}
            if login_request_id:
                browser_plane_adapter.attach_login_resume_context(
                    user_id=int(user_id),
                    workspace=str(workspace),
                    request_id=login_request_id,
                    profile_id=_payload_value(result.get("profile_id")),
                    resume_query=str(resume_query or ""),
                    resume_request=parsed_resume_request,
                    continue_after_confirm=True,
                )
            payload: dict[str, str] = {
                "workspace": str(workspace),
                "tool": next_tool or str(run.name or ""),
                "error": _payload_value(result.get("error")),
                "confirm_kind": _payload_value(result.get("confirm_kind")),
                "action": _payload_value(result.get("action")),
                "resume_query": _payload_value(resume_query),
                "login_request_id": login_request_id,
                "profile_id": _payload_value(result.get("profile_id")),
            }
            if next_call:
                payload["next_call"] = _payload_json(next_call)
            out.append(
                {
                    "kind": "confirm_browser_action",
                    "title": "需要确认后继续浏览器任务",
                    "detail": prompt[:220],
                    **payload,
                }
            )
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
