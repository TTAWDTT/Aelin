from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.services.aelin_loop_message import (
    build_screen_observation_message,
    prepare_tool_result_payload,
    safe_json_loads,
)
from app.services.aelin_loop_types import AgentLoopToolRun, AgentLoopTraceStep
from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage
from app.services.aelin_tools import AelinToolHub


def build_tool_calls_payload(raw_tool_calls: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in raw_tool_calls:
        fn = getattr(tc, "function", None)
        out.append(
            {
                "id": str(getattr(tc, "id", "") or ""),
                "type": "function",
                "function": {
                    "name": str(getattr(fn, "name", "") or "").strip(),
                    "arguments": str(getattr(fn, "arguments", "{}") or "{}"),
                },
            }
        )
    return out


def plan_tool_calls(
    *,
    tool_calls_payload: list[dict[str, Any]],
    policy: AelinToolPolicy,
    usage: ToolPolicyUsage,
) -> tuple[list[dict[str, Any]], bool]:
    planned_calls: list[dict[str, Any]] = []
    reached_total_limit = False
    for tc in tool_calls_payload:
        if usage.total_calls >= policy.max_tool_calls:
            reached_total_limit = True
            break
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        tool_name = str(fn.get("name") or "").strip().lower()
        args = safe_json_loads(str(fn.get("arguments") or "{}"))
        tc_id = str(tc.get("id") or "")
        decision = policy.evaluate(name=tool_name, args=args, usage=usage)
        if decision.allowed:
            usage.round_calls += 1
            usage.total_calls += 1
            if decision.is_write:
                usage.write_calls += 1
        planned_calls.append(
            {
                "tool_name": tool_name,
                "args": args,
                "tc_id": tc_id,
                "policy": decision,
            }
        )
        if decision.allowed and usage.total_calls >= policy.max_tool_calls:
            reached_total_limit = True
            break
    return planned_calls, reached_total_limit


def execute_tool_call(
    *,
    tool_hub: AelinToolHub,
    tool_name: str,
    args: dict[str, Any],
) -> tuple[str, dict[str, Any], str, int]:
    status = "completed"
    result: dict[str, Any] = {}
    error = ""
    started = time.perf_counter()
    try:
        result = tool_hub.execute(tool_name, args)
        if not bool(result.get("ok", True)):
            status = "failed"
            error = str(result.get("error") or "tool_not_ok")[:180]
    except Exception as exc:
        status = "failed"
        error = str(exc)[:180]
        result = {"ok": False, "error": error}
    latency_ms = int((time.perf_counter() - started) * 1000)
    return status, result, error, latency_ms


def append_tool_result(
    *,
    round_index: int,
    tool_name: str,
    args: dict[str, Any],
    tc_id: str,
    is_write: bool,
    status: str,
    result: dict[str, Any],
    error: str,
    latency_ms: int,
    messages: list[dict[str, Any]],
    tool_runs: list[AgentLoopToolRun],
    trace_steps: list[AgentLoopTraceStep],
) -> bool:
    tool_result_for_run, tool_result_for_message, image_data_url = prepare_tool_result_payload(
        tool_name=tool_name,
        status=status,
        result=result,
    )
    tool_runs.append(
        AgentLoopToolRun(
            round_index=round_index,
            name=tool_name,
            args=args,
            status=status,
            result=tool_result_for_run,
            error=error,
            is_write=is_write,
            latency_ms=latency_ms,
        )
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tc_id,
            "content": json.dumps(tool_result_for_message, ensure_ascii=False)[:8000],
        }
    )
    if image_data_url:
        messages.append(build_screen_observation_message(image_data_url))
    trace_steps.append(
        AgentLoopTraceStep(
            stage="agent_loop_tool",
            status=status,
            detail=f"{tool_name}:{error or 'ok'}",
            count=1,
        )
    )
    return status == "completed"


def flush_pending_reads(
    *,
    pending_reads: list[dict[str, Any]],
    tool_hub: AelinToolHub,
    round_index: int,
    messages: list[dict[str, Any]],
    tool_runs: list[AgentLoopToolRun],
    trace_steps: list[AgentLoopTraceStep],
) -> int:
    if not pending_reads:
        return 0
    batch = list(pending_reads)
    pending_reads.clear()
    trace_steps.append(
        AgentLoopTraceStep(
            stage="agent_loop_read_batch",
            status="running",
            detail=f"parallel_reads={len(batch)}",
            count=len(batch),
        )
    )

    results: list[tuple[str, dict[str, Any], str, int] | None] = [None] * len(batch)
    max_workers = max(1, min(4, len(batch)))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="aelin-loop-read") as pool:
        future_map = {
            pool.submit(
                execute_tool_call,
                tool_hub=tool_hub,
                tool_name=str(item.get("tool_name") or ""),
                args=item.get("args") if isinstance(item.get("args"), dict) else {},
            ): idx
            for idx, item in enumerate(batch)
        }
        for future, idx in future_map.items():
            try:
                results[idx] = future.result()
            except Exception as exc:
                results[idx] = ("failed", {"ok": False, "error": str(exc)[:180]}, str(exc)[:180], 0)

    successful_calls = 0
    for idx, item in enumerate(batch):
        tool_name = str(item.get("tool_name") or "")
        tc_id = str(item.get("tc_id") or "")
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        status, result, error, latency_ms = (
            results[idx]
            if isinstance(results[idx], tuple)
            else ("failed", {"ok": False, "error": "unknown"}, "unknown", 0)
        )
        if append_tool_result(
            round_index=round_index,
            tool_name=tool_name,
            args=args,
            tc_id=tc_id,
            is_write=False,
            status=status,
            result=result,
            error=error,
            latency_ms=latency_ms,
            messages=messages,
            tool_runs=tool_runs,
            trace_steps=trace_steps,
        ):
            successful_calls += 1

    trace_steps.append(
        AgentLoopTraceStep(
            stage="agent_loop_read_batch",
            status="completed",
            detail=f"parallel_reads={len(batch)}",
            count=len(batch),
        )
    )
    return successful_calls

