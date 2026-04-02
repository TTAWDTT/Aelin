from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


class DeepAgentsCancelled(RuntimeError):
    """Raised when the surrounding request has been cancelled."""


@dataclass
class DeepAgentsToolRun:
    call_index: int
    name: str
    args: dict[str, Any]
    status: str
    result: dict[str, Any]
    error: str = ""
    is_write: bool = False
    latency_ms: int = 0


@dataclass
class DeepAgentsLoopResult:
    ok: bool
    answer: str
    tool_runs: list[DeepAgentsToolRun] = field(default_factory=list)
    total_calls: int = 0
    write_calls: int = 0
    actions: list[dict[str, str]] = field(default_factory=list)
    error: str = ""
    cancelled: bool = False
    capability_summary: str = ""


def map_tool_runs(raw_tool_runs: list[dict[str, Any]]) -> list[DeepAgentsToolRun]:
    return [
        DeepAgentsToolRun(
            call_index=int(tr.get("call_index", 1)),
            name=str(tr.get("name") or ""),
            args=dict(tr.get("args") or {}),
            status=str(tr.get("status") or ""),
            result=dict(tr.get("result") or {}),
            error=str(tr.get("error") or ""),
            is_write=bool(tr.get("is_write", False)),
            latency_ms=int(tr.get("latency_ms", 0)),
        )
        for tr in raw_tool_runs
    ]


def parse_capabilities_file(files_mapping: dict[str, Any]) -> dict[str, Any]:
    raw = files_mapping.get("/runtime/capabilities.json")
    if not isinstance(raw, dict):
        return {}
    content = raw.get("content")
    if isinstance(content, list):
        text = "\n".join(str(line) for line in content)
    else:
        text = str(content or "")
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_loop_result(
    *,
    ok: bool,
    answer: str = "",
    tool_runs: list[DeepAgentsToolRun] | None = None,
    total_calls: int = 0,
    write_calls: int = 0,
    actions: list[dict[str, str]] | None = None,
    error: str = "",
    cancelled: bool = False,
    capability_summary: str = "",
) -> DeepAgentsLoopResult:
    return DeepAgentsLoopResult(
        ok=ok,
        answer=answer,
        tool_runs=list(tool_runs or []),
        total_calls=int(total_calls or 0),
        write_calls=int(write_calls or 0),
        actions=list(actions or []),
        error=error,
        cancelled=cancelled,
        capability_summary=capability_summary,
    )
