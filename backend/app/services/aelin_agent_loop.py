from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage
from app.services.aelin_tools import AelinToolHub
from app.services.aelin_limits import MAX_IMAGE_DATA_URL_LENGTH
from app.services.llm import LLMService


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_json_loads(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip() != "text":
                continue
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _failed_loop_result(*, stop_reason: str, detail: str) -> "AelinAgentLoopResult":
    return AelinAgentLoopResult(
        ok=False,
        answer="",
        stop_reason=stop_reason,
        rounds=0,
        total_calls=0,
        write_calls=0,
        tool_runs=[],
        trace_steps=[AgentLoopTraceStep(stage="agent_loop", status="failed", detail=detail)],
        actions=[],
        error=stop_reason,
    )


@dataclass
class AgentLoopToolRun:
    round_index: int
    name: str
    args: dict[str, Any]
    status: str
    result: dict[str, Any]
    error: str = ""
    is_write: bool = False
    latency_ms: int = 0


@dataclass
class AgentLoopTraceStep:
    stage: str
    status: str
    detail: str = ""
    count: int = 0
    ts: int = field(default_factory=_now_ms)


@dataclass
class AelinAgentLoopResult:
    ok: bool
    answer: str
    stop_reason: str
    rounds: int
    total_calls: int
    write_calls: int
    tool_runs: list[AgentLoopToolRun]
    trace_steps: list[AgentLoopTraceStep]
    actions: list[dict[str, str]]
    error: str = ""


class AelinAgentLoop:
    def __init__(
        self,
        *,
        service: LLMService,
        provider: str,
        tool_hub: AelinToolHub,
        policy: AelinToolPolicy,
        max_rounds: int,
        round_timeout_seconds: float = 10.0,
        total_timeout_seconds: float = 12.0,
    ) -> None:
        self._service = service
        self._provider = str(provider or "").strip().lower()
        self._tool_hub = tool_hub
        self._policy = policy
        self._max_rounds = max(1, int(max_rounds or 1))
        self._round_timeout_seconds = max(2.0, float(round_timeout_seconds or 10.0))
        self._total_timeout_seconds = max(3.0, float(total_timeout_seconds or 12.0))

    def run(
        self,
        *,
        query: str,
        memory_summary: str,
        history_turns: list[dict[str, str]] | None = None,
        images: list[dict[str, str]] | None = None,
        forced_intent: str = "",
        forced_tool_runs: list[dict[str, Any]] | None = None,
    ) -> AelinAgentLoopResult:
        trace_steps: list[AgentLoopTraceStep] = []
        tool_runs: list[AgentLoopToolRun] = []
        actions: list[dict[str, str]] = []
        usage = ToolPolicyUsage()
        rounds = 0
        stop_reason = "unknown"
        answer = ""

        if self._provider == "rule_based":
            return _failed_loop_result(stop_reason="provider_rule_based", detail="provider_rule_based")
        client = getattr(self._service, "client", None)
        if client is None:
            return _failed_loop_result(stop_reason="llm_not_configured", detail="llm_not_configured")

        tools = self._tool_hub.tool_definitions()
        if not tools:
            return _failed_loop_result(stop_reason="tool_definitions_empty", detail="tool_definitions_empty")

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are Aelin's tool-using assistant. "
                    "Use tools only when needed, keep calls minimal, and provide final Chinese answer once information is enough. "
                    "Never expose hidden reasoning."
                ),
            },
            {
                "role": "system",
                "content": f"memory_summary={str(memory_summary or '')[:1000]}",
            },
        ]
        if forced_intent:
            messages.append(
                {
                    "role": "system",
                    "content": f"forced_intent={str(forced_intent).strip()[:120]}",
                }
            )
        for run in list(forced_tool_runs or [])[:4]:
            name = str(run.get("name") or "").strip().lower()[:64]
            args = run.get("args") if isinstance(run.get("args"), dict) else {}
            result = run.get("result") if isinstance(run.get("result"), dict) else {}
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"forced_tool_result[{name}] "
                        + json.dumps({"args": args, "result": result}, ensure_ascii=False)[:1800]
                    ),
                }
            )
        if history_turns:
            for row in history_turns[-10:]:
                role = str(row.get("role") or "").strip().lower()
                content = str(row.get("content") or "").strip()
                if role in {"user", "assistant"} and content:
                    messages.append({"role": role, "content": content[:3000]})
        query_text = str(query or "").strip()[:1200]
        normalized_images: list[str] = []
        for item in list(images or [])[:4]:
            if not isinstance(item, dict):
                continue
            data_url = str(item.get("data_url") or "").strip()
            if not data_url.startswith("data:image/") or ";base64," not in data_url:
                continue
            if len(data_url) > MAX_IMAGE_DATA_URL_LENGTH:
                continue
            normalized_images.append(data_url)
        if normalized_images:
            user_content: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": query_text or "请先分析我上传的图片，再继续执行工具流程。",
                }
            ]
            for data_url in normalized_images:
                user_content.append({"type": "image_url", "image_url": {"url": data_url}})
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": query_text})
        trace_steps.append(AgentLoopTraceStep(stage="agent_loop", status="running", detail="start", count=0))

        loop_started = time.perf_counter()
        idle_rounds = 0
        for round_index in range(1, self._max_rounds + 1):
            elapsed_total = time.perf_counter() - loop_started
            if elapsed_total >= self._total_timeout_seconds:
                stop_reason = "total_timeout"
                trace_steps.append(
                    AgentLoopTraceStep(
                        stage="agent_loop_round",
                        status="failed",
                        detail=f"total_timeout={self._total_timeout_seconds:.1f}s",
                        count=0,
                    )
                )
                break
            rounds = round_index
            usage.round_calls = 0
            trace_steps.append(AgentLoopTraceStep(stage="agent_loop_round", status="running", detail=f"round={round_index}", count=0))
            try:
                response = client.chat.completions.create(
                    model=self._service.config.model,
                    messages=messages,
                    temperature=self._service.config.temperature,
                    max_tokens=420,
                    tools=tools,
                    tool_choice="auto",
                    timeout=self._round_timeout_seconds,
                )
            except Exception as exc:
                stop_reason = "llm_error"
                trace_steps.append(
                    AgentLoopTraceStep(
                        stage="agent_loop_round",
                        status="failed",
                        detail=f"round={round_index}; llm_error={str(exc)[:160]}",
                        count=0,
                    )
                )
                break

            choice = response.choices[0] if getattr(response, "choices", None) else None
            message = getattr(choice, "message", None) if choice else None
            text_out = _extract_message_text(getattr(message, "content", ""))
            raw_tool_calls = list(getattr(message, "tool_calls", []) or [])

            if not raw_tool_calls:
                answer = text_out
                stop_reason = "final_answer" if answer else "empty_answer"
                trace_steps.append(
                    AgentLoopTraceStep(
                        stage="agent_loop_round",
                        status="completed" if answer else "failed",
                        detail=f"round={round_index}; stop={stop_reason}",
                        count=0,
                    )
                )
                break

            tool_calls_payload: list[dict[str, Any]] = []
            for tc in raw_tool_calls:
                fn = getattr(tc, "function", None)
                tool_calls_payload.append(
                    {
                        "id": str(getattr(tc, "id", "") or ""),
                        "type": "function",
                        "function": {
                            "name": str(getattr(fn, "name", "") or "").strip(),
                            "arguments": str(getattr(fn, "arguments", "{}") or "{}"),
                        },
                    }
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": text_out or "",
                    "tool_calls": tool_calls_payload,
                }
            )

            successful_calls = 0
            planned_calls: list[dict[str, Any]] = []
            reached_total_limit = False
            for tc in tool_calls_payload:
                if usage.total_calls >= self._policy.max_tool_calls:
                    reached_total_limit = True
                    break
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                tool_name = str(fn.get("name") or "").strip().lower()
                args = _safe_json_loads(str(fn.get("arguments") or "{}"))
                tc_id = str(tc.get("id") or "")
                policy = self._policy.evaluate(name=tool_name, args=args, usage=usage)
                if policy.allowed:
                    usage.round_calls += 1
                    usage.total_calls += 1
                    if policy.is_write:
                        usage.write_calls += 1
                planned_calls.append(
                    {
                        "tool_name": tool_name,
                        "args": args,
                        "tc_id": tc_id,
                        "policy": policy,
                    }
                )
                if policy.allowed and usage.total_calls >= self._policy.max_tool_calls:
                    reached_total_limit = True
                    break

            def _run_tool_call(tool_name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any], str, int]:
                status = "completed"
                result: dict[str, Any] = {}
                error = ""
                started = time.perf_counter()
                try:
                    result = self._tool_hub.execute(tool_name, args)
                    if not bool(result.get("ok", True)):
                        status = "failed"
                        error = str(result.get("error") or "tool_not_ok")[:180]
                except Exception as exc:
                    status = "failed"
                    error = str(exc)[:180]
                    result = {"ok": False, "error": error}
                latency_ms = int((time.perf_counter() - started) * 1000)
                return status, result, error, latency_ms

            def _record_tool_result(
                *,
                tool_name: str,
                args: dict[str, Any],
                tc_id: str,
                is_write: bool,
                status: str,
                result: dict[str, Any],
                error: str,
                latency_ms: int,
            ) -> None:
                nonlocal successful_calls
                run = AgentLoopToolRun(
                    round_index=round_index,
                    name=tool_name,
                    args=args,
                    status=status,
                    result=result,
                    error=error,
                    is_write=is_write,
                    latency_ms=latency_ms,
                )
                tool_runs.append(run)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(result, ensure_ascii=False)[:8000],
                    }
                )
                trace_steps.append(
                    AgentLoopTraceStep(
                        stage="agent_loop_tool",
                        status=status,
                        detail=f"{tool_name}:{error or 'ok'}",
                        count=1,
                    )
                )
                if status == "completed":
                    successful_calls += 1

            pending_reads: list[dict[str, Any]] = []

            def _flush_pending_reads() -> None:
                if not pending_reads:
                    return
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
                        pool.submit(_run_tool_call, str(item.get("tool_name") or ""), item.get("args") if isinstance(item.get("args"), dict) else {}): idx
                        for idx, item in enumerate(batch)
                    }
                    for future, idx in future_map.items():
                        try:
                            results[idx] = future.result()
                        except Exception as exc:
                            results[idx] = ("failed", {"ok": False, "error": str(exc)[:180]}, str(exc)[:180], 0)

                for idx, item in enumerate(batch):
                    tool_name = str(item.get("tool_name") or "")
                    tc_id = str(item.get("tc_id") or "")
                    args = item.get("args") if isinstance(item.get("args"), dict) else {}
                    entry = results[idx] if isinstance(results[idx], tuple) else ("failed", {"ok": False, "error": "unknown"}, "unknown", 0)
                    status, result, error, latency_ms = entry
                    _record_tool_result(
                        tool_name=tool_name,
                        args=args,
                        tc_id=tc_id,
                        is_write=False,
                        status=status,
                        result=result,
                        error=error,
                        latency_ms=latency_ms,
                    )

                trace_steps.append(
                    AgentLoopTraceStep(
                        stage="agent_loop_read_batch",
                        status="completed",
                        detail=f"parallel_reads={len(batch)}",
                        count=len(batch),
                    )
                )

            for planned in planned_calls:
                tool_name = str(planned.get("tool_name") or "")
                args = planned.get("args") if isinstance(planned.get("args"), dict) else {}
                tc_id = str(planned.get("tc_id") or "")
                policy = planned.get("policy")
                is_write = bool(getattr(policy, "is_write", False))
                allowed = bool(getattr(policy, "allowed", False))
                reason = str(getattr(policy, "reason", "") or "")

                if allowed and (not is_write):
                    pending_reads.append(planned)
                    continue

                _flush_pending_reads()
                if not allowed:
                    _record_tool_result(
                        tool_name=tool_name,
                        args=args,
                        tc_id=tc_id,
                        is_write=is_write,
                        status="failed",
                        result={"ok": False, "error": f"policy:{reason}"},
                        error=f"policy:{reason}",
                        latency_ms=0,
                    )
                    continue
                status, result, error, latency_ms = _run_tool_call(tool_name, args)
                _record_tool_result(
                    tool_name=tool_name,
                    args=args,
                    tc_id=tc_id,
                    is_write=is_write,
                    status=status,
                    result=result,
                    error=error,
                    latency_ms=latency_ms,
                )

            _flush_pending_reads()

            if successful_calls <= 0:
                idle_rounds += 1
            else:
                idle_rounds = 0
            trace_steps.append(
                AgentLoopTraceStep(
                    stage="agent_loop_round",
                    status="completed",
                    detail=f"round={round_index}; calls={usage.round_calls}; successful={successful_calls}",
                    count=usage.round_calls,
                )
            )
            if reached_total_limit or usage.total_calls >= self._policy.max_tool_calls:
                stop_reason = "total_call_limit"
                break
            if idle_rounds >= 2:
                stop_reason = "no_progress"
                break

        if not stop_reason or stop_reason == "unknown":
            stop_reason = "max_rounds"

        if not answer:
            if stop_reason == "total_timeout":
                answer = "我已达到本轮时限，先返回阶段性结论。你可以缩小问题范围后我继续执行。"
            else:
                answer = self._final_answer(messages, query=query)
                if answer and stop_reason == "empty_answer":
                    stop_reason = "finalized_after_tools"

        actions = self._build_actions(tool_runs)
        trace_steps.append(
            AgentLoopTraceStep(
                stage="agent_loop",
                status="completed" if answer else "failed",
                detail=f"stop={stop_reason}; rounds={rounds}; calls={usage.total_calls}",
                count=usage.total_calls,
            )
        )
        return AelinAgentLoopResult(
            ok=bool(answer),
            answer=answer,
            stop_reason=stop_reason,
            rounds=rounds,
            total_calls=usage.total_calls,
            write_calls=usage.write_calls,
            tool_runs=tool_runs,
            trace_steps=trace_steps,
            actions=actions,
            error="" if answer else "empty_answer",
        )

    def _final_answer(self, messages: list[dict[str, Any]], *, query: str) -> str:
        try:
            final_messages = list(messages)
            final_messages.append(
                {
                    "role": "user",
                    "content": "请基于已完成的工具结果，直接给出最终中文回答。不要继续调用工具。",
                }
            )
            response = self._service.client.chat.completions.create(
                model=self._service.config.model,
                messages=final_messages,
                temperature=self._service.config.temperature,
                max_tokens=420,
                timeout=self._round_timeout_seconds,
            )
            choice = response.choices[0] if getattr(response, "choices", None) else None
            message = getattr(choice, "message", None) if choice else None
            text_out = _extract_message_text(getattr(message, "content", ""))
            if text_out:
                return text_out
        except Exception:
            pass
        return self._fallback_answer(query=query)

    def _fallback_answer(self, *, query: str) -> str:
        safe_q = str(query or "").strip()
        if safe_q:
            return f"我已经执行了受控工具流程，但当前无法稳定产出结果。请重试一次：{safe_q[:120]}"
        return "我已经执行了受控工具流程，但当前无法稳定产出结果。请重试一次。"

    def _build_actions(self, runs: list[AgentLoopToolRun]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for run in runs:
            if run.status != "completed":
                continue
            result = run.result if isinstance(run.result, dict) else {}
            if run.name == "tracking" and int(result.get("target_id") or 0) > 0:
                target_id = int(result.get("target_id") or 0)
                out.append(
                    {
                        "kind": "open_tracking",
                        "title": "已创建追踪",
                        "detail": str(result.get("target") or f"target_id={target_id}")[:120],
                        "target_id": str(target_id),
                        "workspace": str(self._tool_hub.workspace),
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
                            "workspace": str(self._tool_hub.workspace),
                        }
                    )
            if len(out) >= 4:
                break
        return out
