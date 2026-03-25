from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.aelin.tool_hub import AelinToolHub
from app.services.aelin.tool_policy import AelinToolPolicy
from app.services.deepagents.deepagents_graph import DeepAgentsCancelled, build_chat_agent
from app.services.deepagents.cancel_utils import is_cancelled
from app.services.deepagents.input_mapping import build_invoke_payload
from app.services.deepagents.output_utils import extract_answer

_log = logging.getLogger(__name__)


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
    memory_snapshot: str = ""
    capability_summary: str = ""


def _map_tool_runs(raw_tool_runs: list[dict[str, Any]]) -> list[DeepAgentsToolRun]:
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


def _assert_not_cancelled(cancel_token: Any | None) -> None:
    if is_cancelled(cancel_token):
        raise DeepAgentsCancelled("cancelled")


def _parse_capabilities_file(files_mapping: dict[str, Any]) -> dict[str, Any]:
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


def _result(
    *,
    ok: bool,
    answer: str = "",
    tool_runs: list[DeepAgentsToolRun] | None = None,
    total_calls: int = 0,
    write_calls: int = 0,
    actions: list[dict[str, str]] | None = None,
    error: str = "",
    cancelled: bool = False,
    memory_snapshot: str = "",
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
        memory_snapshot=memory_snapshot,
        capability_summary=capability_summary,
    )


def run_deepagents_loop(
    *,
    service: LLMService,
    provider: str,
    tool_hub: AelinToolHub,
    policy: AelinToolPolicy,
    query: str,
    memory_summary: str,
    history_turns: list[dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
    cancel_token: Any | None = None,
) -> DeepAgentsLoopResult:
    try:
        _assert_not_cancelled(cancel_token)
        agent, usage, raw_tool_runs, files_mapping = build_chat_agent(
            service=service,
            provider=provider,
            tool_hub=tool_hub,
            policy=policy,
            memory_summary=memory_summary,
            cancel_token=cancel_token,
        )
        if agent is None:
            return _result(
                ok=False,
                error="llm_not_configured",
                memory_snapshot="",
            )

        capabilities = _parse_capabilities_file(files_mapping)
        capability_summary = (
            f"tools={len(list(capabilities.get('tools') or []))}; "
            f"skills={len(list(capabilities.get('mounted_skills') or []))}; "
            f"memory_files={len(list(capabilities.get('memory_files') or []))}"
        )

        invoke_payload = build_invoke_payload(
            query=query,
            history_turns=history_turns,
            images=images,
            files_mapping=files_mapping,
        )

        _assert_not_cancelled(cancel_token)
        response = agent.invoke(invoke_payload)
        _assert_not_cancelled(cancel_token)

        answer = extract_answer(response).strip()
        tool_runs = _map_tool_runs(raw_tool_runs)

        if not answer:
            return _result(
                ok=False,
                tool_runs=tool_runs,
                total_calls=getattr(usage, "total_calls", 0),
                write_calls=getattr(usage, "write_calls", 0),
                error="empty_answer_from_deepagents",
                memory_snapshot=memory_summary,
                capability_summary=capability_summary,
            )

        return _result(
            ok=True,
            answer=answer,
            tool_runs=tool_runs,
            total_calls=getattr(usage, "total_calls", 0),
            write_calls=getattr(usage, "write_calls", 0),
            memory_snapshot=memory_summary,
            capability_summary=capability_summary,
        )
    except DeepAgentsCancelled:
        return _result(
            ok=False,
            cancelled=True,
            error="cancelled",
            memory_snapshot=memory_summary,
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception("deepagents_unhandled_error provider=%s", provider)
        return _result(
            ok=False,
            error=f"deepagents_unhandled_error:{str(exc)[:160]}",
            memory_snapshot=memory_summary,
        )
