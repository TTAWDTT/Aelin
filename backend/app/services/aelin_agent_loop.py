from __future__ import annotations

import logging
import time
from typing import Any

from app.services.aelin_loop_actions import build_actions as _build_actions_from_runs
from app.services.aelin_loop_logging import safe_preview
from app.services.aelin_loop_message import build_initial_messages, extract_message_text
from app.services.aelin_loop_round import request_round_response
from app.services.aelin_loop_tools import (
    append_tool_result,
    build_tool_calls_payload,
    execute_tool_call,
    flush_pending_reads,
    plan_tool_calls,
)
from app.services.aelin_loop_types import (
    AelinAgentLoopResult,
    AgentLoopToolRun,
    AgentLoopTraceStep,
)
from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage
from app.services.aelin_tools import AelinToolHub
from app.services.llm import LLMService

_LOG = logging.getLogger(__name__)
_SERIAL_READ_TOOLS = {"browser_state_get", "browser_session_list"}


def _failed_loop_result(*, stop_reason: str, detail: str) -> AelinAgentLoopResult:
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
        attachment_ids: list[int] | None = None,
        forced_intent: str = "",
        forced_tool_runs: list[dict[str, Any]] | None = None,
    ) -> AelinAgentLoopResult:
        trace_steps: list[AgentLoopTraceStep] = []
        tool_runs: list[AgentLoopToolRun] = []
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

        _LOG.info(
            "agent_loop start provider=%s max_rounds=%s history_turns=%s images=%s query=%s",
            self._provider,
            self._max_rounds,
            len(history_turns or []),
            len(images or []),
            safe_preview(query),
        )
        messages = build_initial_messages(
            query=query,
            memory_summary=memory_summary,
            history_turns=history_turns,
            images=images,
            attachment_ids=attachment_ids,
            forced_intent=forced_intent,
            forced_tool_runs=forced_tool_runs,
        )
        retried_without_images = False
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
            response, retried_without_images, llm_error_reason = request_round_response(
                client=client,
                service=self._service,
                messages=messages,
                tools=tools,
                round_timeout_seconds=self._round_timeout_seconds,
                round_index=round_index,
                trace_steps=trace_steps,
                retried_without_images=retried_without_images,
            )
            if llm_error_reason:
                stop_reason = llm_error_reason
                break
            if response is None:
                stop_reason = "llm_error"
                break

            choice = response.choices[0] if getattr(response, "choices", None) else None
            message = getattr(choice, "message", None) if choice else None
            text_out = extract_message_text(getattr(message, "content", ""))
            raw_tool_calls = list(getattr(message, "tool_calls", []) or [])

            if not raw_tool_calls:
                answer = text_out
                stop_reason = "final_answer" if answer else "empty_answer"
                _LOG.info(
                    "agent_loop round_final_answer round=%s stop=%s text=%s",
                    round_index,
                    stop_reason,
                    safe_preview(answer),
                )
                trace_steps.append(
                    AgentLoopTraceStep(
                        stage="agent_loop_round",
                        status="completed" if answer else "failed",
                        detail=f"round={round_index}; stop={stop_reason}",
                        count=0,
                    )
                )
                break

            tool_calls_payload = build_tool_calls_payload(raw_tool_calls)
            messages.append(
                {
                    "role": "assistant",
                    "content": text_out or "",
                    "tool_calls": tool_calls_payload,
                }
            )

            successful_calls = 0
            planned_calls, reached_total_limit = plan_tool_calls(
                tool_calls_payload=tool_calls_payload,
                policy=self._policy,
                usage=usage,
            )
            pending_reads: list[dict[str, Any]] = []

            for planned in planned_calls:
                tool_name = str(planned.get("tool_name") or "")
                args = planned.get("args") if isinstance(planned.get("args"), dict) else {}
                tc_id = str(planned.get("tc_id") or "")
                policy = planned.get("policy")
                is_write = bool(getattr(policy, "is_write", False))
                allowed = bool(getattr(policy, "allowed", False))
                reason = str(getattr(policy, "reason", "") or "")

                if allowed and (not is_write):
                    if tool_name in _SERIAL_READ_TOOLS:
                        successful_calls += flush_pending_reads(
                            pending_reads=pending_reads,
                            tool_hub=self._tool_hub,
                            round_index=round_index,
                            messages=messages,
                            tool_runs=tool_runs,
                            trace_steps=trace_steps,
                        )
                        status, result, error, latency_ms = execute_tool_call(
                            tool_hub=self._tool_hub,
                            tool_name=tool_name,
                            args=args,
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
                        continue
                    pending_reads.append(planned)
                    continue

                successful_calls += flush_pending_reads(
                    pending_reads=pending_reads,
                    tool_hub=self._tool_hub,
                    round_index=round_index,
                    messages=messages,
                    tool_runs=tool_runs,
                    trace_steps=trace_steps,
                )
                if not allowed:
                    if append_tool_result(
                        round_index=round_index,
                        tool_name=tool_name,
                        args=args,
                        tc_id=tc_id,
                        is_write=is_write,
                        status="failed",
                        result={"ok": False, "error": f"policy:{reason}"},
                        error=f"policy:{reason}",
                        latency_ms=0,
                        messages=messages,
                        tool_runs=tool_runs,
                        trace_steps=trace_steps,
                    ):
                        successful_calls += 1
                    continue

                status, result, error, latency_ms = execute_tool_call(
                    tool_hub=self._tool_hub,
                    tool_name=tool_name,
                    args=args,
                )
                if append_tool_result(
                    round_index=round_index,
                    tool_name=tool_name,
                    args=args,
                    tc_id=tc_id,
                    is_write=is_write,
                    status=status,
                    result=result,
                    error=error,
                    latency_ms=latency_ms,
                    messages=messages,
                    tool_runs=tool_runs,
                    trace_steps=trace_steps,
                ):
                    successful_calls += 1

            successful_calls += flush_pending_reads(
                pending_reads=pending_reads,
                tool_hub=self._tool_hub,
                round_index=round_index,
                messages=messages,
                tool_runs=tool_runs,
                trace_steps=trace_steps,
            )

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
        _LOG.info(
            "agent_loop end stop=%s rounds=%s total_calls=%s write_calls=%s answer=%s",
            stop_reason,
            rounds,
            usage.total_calls,
            usage.write_calls,
            safe_preview(answer),
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
            _LOG.info("agent_loop final_answer_request messages=%s", len(final_messages))
            response = self._service.client.chat.completions.create(
                model=self._service.config.model,
                messages=final_messages,
                temperature=self._service.config.temperature,
                max_tokens=420,
                timeout=self._round_timeout_seconds,
            )
            choice = response.choices[0] if getattr(response, "choices", None) else None
            message = getattr(choice, "message", None) if choice else None
            text_out = extract_message_text(getattr(message, "content", ""))
            if text_out:
                _LOG.info("agent_loop final_answer_response text=%s", safe_preview(text_out))
                return text_out
        except Exception as exc:
            _LOG.warning("agent_loop final_answer_failed error=%s", str(exc)[:200])
        return self._fallback_answer(query=query)

    def _fallback_answer(self, *, query: str) -> str:
        safe_q = str(query or "").strip()
        if safe_q:
            return f"我已经执行了受控工具流程，但当前无法稳定产出结果。请重试一次：{safe_q[:120]}"
        return "我已经执行了受控工具流程，但当前无法稳定产出结果。请重试一次。"

    def _build_actions(self, runs: list[AgentLoopToolRun]) -> list[dict[str, str]]:
        return _build_actions_from_runs(runs=runs, workspace=str(self._tool_hub.workspace))
