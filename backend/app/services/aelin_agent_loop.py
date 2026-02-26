from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage
from app.services.aelin_tools import AelinToolHub
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
    ) -> None:
        self._service = service
        self._provider = str(provider or "").strip().lower()
        self._tool_hub = tool_hub
        self._policy = policy
        self._max_rounds = max(1, int(max_rounds or 1))

    def run(
        self,
        *,
        query: str,
        memory_summary: str,
        history_turns: list[dict[str, str]] | None = None,
    ) -> AelinAgentLoopResult:
        trace_steps: list[AgentLoopTraceStep] = []
        tool_runs: list[AgentLoopToolRun] = []
        actions: list[dict[str, str]] = []
        usage = ToolPolicyUsage()
        rounds = 0
        stop_reason = "unknown"
        answer = ""

        if self._provider == "rule_based":
            return AelinAgentLoopResult(
                ok=False,
                answer="",
                stop_reason="provider_rule_based",
                rounds=0,
                total_calls=0,
                write_calls=0,
                tool_runs=[],
                trace_steps=[AgentLoopTraceStep(stage="agent_loop", status="failed", detail="provider_rule_based")],
                actions=[],
                error="provider_rule_based",
            )
        client = getattr(self._service, "client", None)
        if client is None:
            return AelinAgentLoopResult(
                ok=False,
                answer="",
                stop_reason="llm_not_configured",
                rounds=0,
                total_calls=0,
                write_calls=0,
                tool_runs=[],
                trace_steps=[AgentLoopTraceStep(stage="agent_loop", status="failed", detail="llm_not_configured")],
                actions=[],
                error="llm_not_configured",
            )

        tools = self._tool_hub.tool_definitions()
        if not tools:
            return AelinAgentLoopResult(
                ok=False,
                answer="",
                stop_reason="tool_definitions_empty",
                rounds=0,
                total_calls=0,
                write_calls=0,
                tool_runs=[],
                trace_steps=[AgentLoopTraceStep(stage="agent_loop", status="failed", detail="tool_definitions_empty")],
                actions=[],
                error="tool_definitions_empty",
            )

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
        if history_turns:
            for row in history_turns[-10:]:
                role = str(row.get("role") or "").strip().lower()
                content = str(row.get("content") or "").strip()
                if role in {"user", "assistant"} and content:
                    messages.append({"role": role, "content": content[:3000]})
        messages.append({"role": "user", "content": str(query or "").strip()[:1200]})
        trace_steps.append(AgentLoopTraceStep(stage="agent_loop", status="running", detail="start", count=0))

        idle_rounds = 0
        for round_index in range(1, self._max_rounds + 1):
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
            text_out = str(getattr(message, "content", "") or "").strip()
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
            for tc in tool_calls_payload:
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                tool_name = str(fn.get("name") or "").strip().lower()
                args = _safe_json_loads(str(fn.get("arguments") or "{}"))
                tc_id = str(tc.get("id") or "")
                policy = self._policy.evaluate(name=tool_name, args=args, usage=usage)
                usage.round_calls += 1
                usage.total_calls += 1

                status = "completed"
                result: dict[str, Any] = {}
                error = ""
                started = time.perf_counter()

                if not policy.allowed:
                    status = "failed"
                    error = f"policy:{policy.reason}"
                    result = {"ok": False, "error": error}
                else:
                    try:
                        result = self._tool_hub.execute(tool_name, args)
                        if not bool(result.get("ok", True)):
                            status = "failed"
                            error = str(result.get("error") or "tool_not_ok")[:180]
                        else:
                            successful_calls += 1
                        if policy.is_write:
                            usage.write_calls += 1
                    except Exception as exc:
                        status = "failed"
                        error = str(exc)[:180]
                        result = {"ok": False, "error": error}

                latency_ms = int((time.perf_counter() - started) * 1000)
                run = AgentLoopToolRun(
                    round_index=round_index,
                    name=tool_name,
                    args=args,
                    status=status,
                    result=result,
                    error=error,
                    is_write=policy.is_write,
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

                if usage.total_calls >= self._policy.max_tool_calls:
                    break

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
            if usage.total_calls >= self._policy.max_tool_calls:
                stop_reason = "total_call_limit"
                break
            if idle_rounds >= 2:
                stop_reason = "no_progress"
                break

        if not stop_reason or stop_reason == "unknown":
            stop_reason = "max_rounds"

        if not answer:
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
        client = getattr(self._service, "client", None)
        if client is None:
            return self._fallback_answer(query=query)
        try:
            final_messages = list(messages)
            final_messages.append(
                {
                    "role": "user",
                    "content": "请基于已完成的工具结果，直接给出最终中文回答。不要继续调用工具。",
                }
            )
            response = client.chat.completions.create(
                model=self._service.config.model,
                messages=final_messages,
                temperature=self._service.config.temperature,
                max_tokens=420,
            )
            choice = response.choices[0] if getattr(response, "choices", None) else None
            message = getattr(choice, "message", None) if choice else None
            text_out = str(getattr(message, "content", "") or "").strip()
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

