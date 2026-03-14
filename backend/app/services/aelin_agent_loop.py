from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.services.aelin_loop_actions import build_actions as _build_actions_from_runs
from app.services.aelin_loop_logging import safe_preview
from app.services.aelin_loop_message import build_initial_messages, extract_message_text
from app.services.aelin_planes import list_plane_artifacts, list_plane_events
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
_SERIAL_READ_TOOLS: set[str] = {"plane"}
_ACTIVE_PLANE_STATES = {"queued", "running", "waiting_user", "blocked"}
_TERMINAL_PLANE_STATES = {"completed", "failed", "closed"}


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


def _summarize_resume_images(images: list[dict[str, str]] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in list(images or [])[:4]:
        if not isinstance(raw, dict):
            continue
        data_url = str(raw.get("data_url") or "")
        mime_type = ""
        if data_url.startswith("data:"):
            head = data_url[5:].split(",", 1)[0]
            mime_type = head.split(";", 1)[0][:80]
        byte_length = 0
        if "base64," in data_url:
            base64_payload = data_url.split("base64,", 1)[1]
            byte_length = max(0, (len(base64_payload.rstrip("=")) * 3) // 4)
        items.append(
            {
                "name": str(raw.get("name") or "")[:120],
                "mime_type": mime_type,
                "byte_length": byte_length,
                "has_data_url": bool(data_url),
            }
        )
    return items


def _build_resume_request_payload(
    *,
    query: str,
    workspace: str,
    history_turns: list[dict[str, str]] | None,
    images: list[dict[str, str]] | None,
    attachment_ids: list[int] | None,
) -> dict[str, Any]:
    return {
        "query": str(query or "")[:1200],
        "workspace": str(workspace or "default")[:64],
        "use_memory": True,
        "history": list(history_turns or [])[:20],
        "attachment_ids": [int(item) for item in list(attachment_ids or [])[:20] if int(item) > 0],
        # The actual image binaries are not required for login resumption.
        "images": [],
        "image_summaries": _summarize_resume_images(images),
    }


def _extract_confirmation_request(
    *,
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    query: str,
) -> dict[str, Any] | None:
    # Browser plane 已移除，当前不在 Agent Loop 内触发浏览器交互确认。
    return None


def _plane_task_snapshot_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    task_id = " ".join(str(payload.get("task_id") or "").strip().split())[:96]
    if not task_id:
        return None
    plane = str(payload.get("plane") or "").strip().lower()[:32] or "browser"
    state = str(payload.get("state") or "").strip().lower()[:32]
    return {
        "task_id": task_id,
        "plane": plane,
        "state": state,
        "summary": str(payload.get("summary") or "")[:260],
        "user_prompt": str(payload.get("user_prompt") or "")[:260],
        "requires_user_input": bool(payload.get("requires_user_input")),
        "last_url": str(payload.get("last_url") or "")[:260],
    }


def _supervised_plane_from_forced_tool_runs(forced_tool_runs: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    for row in reversed(list(forced_tool_runs or [])):
        if str(row.get("name") or "").strip().lower() != "plane":
            continue
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        snapshot = _plane_task_snapshot_from_payload(result)
        if snapshot is not None:
            return snapshot
    return None


def _update_supervised_plane_task(
    current: dict[str, Any] | None,
    *,
    tool_name: str,
    status: str,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    if str(tool_name or "").strip().lower() != "plane":
        return current
    if str(status or "").strip().lower() != "completed":
        return current
    snapshot = _plane_task_snapshot_from_payload(result)
    return snapshot if snapshot is not None else current


def _build_plane_runtime_context_message(
    *,
    tool_hub: AelinToolHub,
    result: dict[str, Any],
) -> str:
    snapshot = _plane_task_snapshot_from_payload(result)
    if snapshot is None:
        return ""
    if str(snapshot.get("state") or "") not in _TERMINAL_PLANE_STATES:
        return ""

    task_id = str(snapshot.get("task_id") or "")
    plane = str(snapshot.get("plane") or "browser")
    workspace = str(getattr(tool_hub, "workspace", "default") or "default")
    user_id = int(getattr(tool_hub, "user_id", 0) or 0)
    db = getattr(tool_hub, "db", None)

    event_lines: list[str] = []
    artifact_lines: list[str] = []
    if db is not None and user_id > 0:
        try:
            for row in list_plane_events(
                task_id,
                user_id=user_id,
                workspace=workspace,
                plane=plane,
                db=db,
                limit=6,
            ):
                event_type = str(row.get("event_type") or "").strip()
                summary = str(row.get("summary") or "").strip()
                event_lines.append(f"- {event_type}: {summary[:120] or 'event'}")
        except Exception:
            event_lines = []
        try:
            for row in list_plane_artifacts(
                task_id,
                user_id=user_id,
                workspace=workspace,
                plane=plane,
                db=db,
                limit=6,
            ):
                kind = str(row.get("kind") or "").strip()
                content = row.get("content") if isinstance(row.get("content"), dict) else {}
                preview = ""
                if kind == "page_text":
                    preview = str(content.get("text") or "").strip()[:200]
                elif kind == "page_location":
                    preview = str(content.get("url") or "").strip()[:200]
                else:
                    preview = str(content)[:200]
                artifact_lines.append(f"- {kind}: {preview or 'artifact'}")
        except Exception:
            artifact_lines = []

    if not event_lines:
        event_lines = [f"- terminal_state: {str(snapshot.get('state') or '')}"]
    if not artifact_lines:
        fallback_artifacts: list[str] = []
        last_url = str(result.get("last_url") or "").strip()
        last_text = str(result.get("last_text") or "").strip()
        if last_url:
            fallback_artifacts.append(f"- page_location: {last_url[:200]}")
        if last_text:
            fallback_artifacts.append(f"- page_text: {last_text[:200]}")
        artifact_lines = fallback_artifacts or ["- none"]

    lines = [
        "[AELIN PLANE RUNTIME]",
        f"plane={plane}",
        f"task_id={task_id}",
        f"state={str(snapshot.get('state') or '')}",
        f"summary={str(snapshot.get('summary') or '')[:260]}",
        "events:",
        *event_lines[:6],
        "artifacts:",
        *artifact_lines[:6],
    ]
    return "\n".join(lines).strip()


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
        max_plane_supervision_calls_per_round: int = 1,
        max_plane_supervision_calls: int = 6,
    ) -> None:
        self._service = service
        self._provider = str(provider or "").strip().lower()
        self._tool_hub = tool_hub
        self._policy = policy
        self._max_rounds = max(1, int(max_rounds or 1))
        self._round_timeout_seconds = max(2.0, float(round_timeout_seconds or 10.0))
        self._total_timeout_seconds = max(3.0, float(total_timeout_seconds or 12.0))
        self._max_plane_supervision_calls_per_round = max(1, int(max_plane_supervision_calls_per_round or 1))
        self._max_plane_supervision_calls = max(1, int(max_plane_supervision_calls or 1))

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
        tool_skill_bodies: list[str] | None = None,
        cancel_token: Any | None = None,
    ) -> AelinAgentLoopResult:
        self._last_query = str(query or "")
        self._resume_request_json = json.dumps(
            _build_resume_request_payload(
                query=query,
                workspace=str(self._tool_hub.workspace or "default"),
                history_turns=history_turns,
                images=images,
                attachment_ids=attachment_ids,
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        trace_steps: list[AgentLoopTraceStep] = []
        tool_runs: list[AgentLoopToolRun] = []
        usage = ToolPolicyUsage()
        rounds = 0
        stop_reason = "unknown"
        answer = ""
        pending_confirmation: dict[str, Any] | None = None
        supervised_plane_task = _supervised_plane_from_forced_tool_runs(forced_tool_runs)
        waiting_plane_resume_probe_pending = bool(
            isinstance(supervised_plane_task, dict)
            and str(supervised_plane_task.get("state") or "") == "waiting_user"
        )
        plane_supervision_calls_total = 0

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
            tool_skill_bodies=tool_skill_bodies,
        )
        retried_without_images = False
        trace_steps.append(AgentLoopTraceStep(stage="agent_loop", status="running", detail="start", count=0))

        loop_started = time.perf_counter()
        idle_rounds = 0
        for round_index in range(1, self._max_rounds + 1):
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                stop_reason = "client_disconnected"
                trace_steps.append(
                    AgentLoopTraceStep(
                        stage="agent_loop_round",
                        status="failed",
                        detail=f"round={round_index}; stop=client_disconnected",
                        count=0,
                    )
                )
                break
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
            plane_supervision_calls_round = 0
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
                active_plane = (
                    dict(supervised_plane_task)
                    if isinstance(supervised_plane_task, dict)
                    and str(supervised_plane_task.get("state") or "") in _ACTIVE_PLANE_STATES
                    else None
                )
                if active_plane is not None:
                    if str(active_plane.get("state") or "") == "waiting_user":
                        if not waiting_plane_resume_probe_pending:
                            answer = str(active_plane.get("user_prompt") or "").strip() or "当前网页任务需要你先完成人工操作后我再继续。"
                            stop_reason = "plane_waiting_user"
                            trace_steps.append(
                                AgentLoopTraceStep(
                                    stage="agent_loop_plane",
                                    status="completed",
                                    detail=f"task={active_plane.get('task_id')}; state=waiting_user",
                                    count=1,
                                )
                            )
                            break
                        waiting_plane_resume_probe_pending = False
                    if plane_supervision_calls_total >= self._max_plane_supervision_calls:
                        stop_reason = "plane_supervision_limit"
                        trace_steps.append(
                            AgentLoopTraceStep(
                                stage="agent_loop_plane",
                                status="failed",
                                detail=f"task={active_plane.get('task_id')}; scope=total",
                                count=0,
                            )
                        )
                        break
                    if plane_supervision_calls_round >= self._max_plane_supervision_calls_per_round:
                        stop_reason = "plane_supervision_limit"
                        trace_steps.append(
                            AgentLoopTraceStep(
                                stage="agent_loop_plane",
                                status="failed",
                                detail=f"task={active_plane.get('task_id')}; scope=round",
                                count=0,
                            )
                        )
                        break
                    plane_supervision_calls_total += 1
                    plane_supervision_calls_round += 1
                    trace_steps.append(
                        AgentLoopTraceStep(
                            stage="agent_loop_plane",
                            status="running",
                            detail=f"task={active_plane.get('task_id')}; action=status",
                            count=1,
                        )
                    )
                    status, result, error, latency_ms = execute_tool_call(
                        tool_hub=self._tool_hub,
                        tool_name="plane",
                        args={
                            "action": "status",
                            "plane": str(active_plane.get("plane") or "browser"),
                            "task_id": str(active_plane.get("task_id") or ""),
                        },
                    )
                    # For supervision-driven plane.status calls we only record the
                    # run and tracing metadata; we deliberately avoid emitting a
                    # model-visible tool message because本轮并没有对应的
                    # assistant.tool_calls，防止产生不合法的对话序列。
                    tool_runs.append(
                        AgentLoopToolRun(
                            round_index=round_index,
                            name="plane",
                            args={
                                "action": "status",
                                "plane": str(active_plane.get("plane") or "browser"),
                                "task_id": str(active_plane.get("task_id") or ""),
                            },
                            status=status,
                            result=result,
                            error=error,
                            is_write=False,
                            latency_ms=latency_ms,
                        )
                    )
                    trace_steps.append(
                        AgentLoopTraceStep(
                            stage="agent_loop_tool",
                            status=status,
                            detail=f"plane:{error or 'ok'}",
                            count=1,
                        )
                    )
                    if status == "completed":
                        supervised_plane_task = _update_supervised_plane_task(
                            supervised_plane_task,
                            tool_name="plane",
                            status=status,
                            result=result,
                        )
                        runtime_context = _build_plane_runtime_context_message(
                            tool_hub=self._tool_hub,
                            result=result,
                        )
                        if runtime_context:
                            messages.append({"role": "system", "content": runtime_context})
                        if (
                            isinstance(supervised_plane_task, dict)
                            and str(supervised_plane_task.get("state") or "") == "waiting_user"
                        ):
                            waiting_plane_resume_probe_pending = False
                    continue
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
                if pending_confirmation is not None:
                    break
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
                            supervised_plane_task = _update_supervised_plane_task(
                                supervised_plane_task,
                                tool_name=tool_name,
                                status=status,
                                result=result,
                            )
                            runtime_context = _build_plane_runtime_context_message(
                                tool_hub=self._tool_hub,
                                result=result,
                            )
                            if runtime_context:
                                messages.append({"role": "system", "content": runtime_context})
                            if (
                                isinstance(supervised_plane_task, dict)
                                and str(supervised_plane_task.get("state") or "") == "waiting_user"
                            ):
                                waiting_plane_resume_probe_pending = False
                        if pending_confirmation is None:
                            pending_confirmation = _extract_confirmation_request(
                                tool_name=tool_name,
                                args=args,
                                result=result,
                                query=query,
                            )
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
                    supervised_plane_task = _update_supervised_plane_task(
                        supervised_plane_task,
                        tool_name=tool_name,
                        status=status,
                        result=result,
                    )
                    runtime_context = _build_plane_runtime_context_message(
                        tool_hub=self._tool_hub,
                        result=result,
                    )
                    if runtime_context:
                        messages.append({"role": "system", "content": runtime_context})
                    if (
                        isinstance(supervised_plane_task, dict)
                        and str(supervised_plane_task.get("state") or "") == "waiting_user"
                    ):
                        waiting_plane_resume_probe_pending = False
                if pending_confirmation is None:
                    pending_confirmation = _extract_confirmation_request(
                        tool_name=tool_name,
                        args=args,
                        result=result,
                        query=query,
                    )

            if pending_confirmation is not None:
                stop_reason = "requires_confirmation"
                trace_steps.append(
                    AgentLoopTraceStep(
                        stage="agent_loop_confirm",
                        status="completed",
                        detail=f"tool={pending_confirmation.get('tool')}; kind={pending_confirmation.get('confirm_kind') or '-'}",
                        count=1,
                    )
                )
                break
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
                    detail=f"round={round_index}; calls={usage.round_calls + plane_supervision_calls_round}; successful={successful_calls}",
                    count=usage.round_calls + plane_supervision_calls_round,
                )
            )
            active_plane_after_round = (
                dict(supervised_plane_task)
                if isinstance(supervised_plane_task, dict)
                and str(supervised_plane_task.get("state") or "") in _ACTIVE_PLANE_STATES
                else None
            )
            if (reached_total_limit or usage.total_calls >= self._policy.max_tool_calls) and active_plane_after_round is None:
                stop_reason = "total_call_limit"
                break
            if idle_rounds >= 2:
                stop_reason = "no_progress"
                break

        if not stop_reason or stop_reason == "unknown":
            stop_reason = "max_rounds"

        if not answer:
            if pending_confirmation is not None:
                answer = str(pending_confirmation.get("user_prompt") or "").strip()
                stop_reason = "requires_confirmation"
            elif stop_reason == "total_timeout":
                answer = "我已达到本轮时限，先返回阶段性结论。你可以缩小问题范围后我继续执行。"
            elif (usage.total_calls > 0 or plane_supervision_calls_total > 0) and stop_reason in {"total_call_limit", "plane_supervision_limit", "no_progress", "max_rounds"}:
                answer = self._partial_answer_from_runs(tool_runs=tool_runs, query=query)
                stop_reason = "partial_result"
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
            usage.total_calls + plane_supervision_calls_total,
            usage.write_calls,
            safe_preview(answer),
        )
        return AelinAgentLoopResult(
            ok=bool(answer),
            answer=answer,
            stop_reason=stop_reason,
            rounds=rounds,
            total_calls=usage.total_calls + plane_supervision_calls_total,
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
                max_tokens=320,
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

    def _partial_answer_from_runs(self, *, tool_runs: list[AgentLoopToolRun], query: str) -> str:
        if not tool_runs:
            return self._fallback_answer(query=query)
        lines: list[str] = []
        for run in list(reversed(tool_runs)):
            if run.status != "completed":
                continue
            result = run.result if isinstance(run.result, dict) else {}
            summary = str(
                result.get("effect_summary")
                or result.get("summary")
                or result.get("message")
                or result.get("error")
                or ""
            ).strip()
            lines.append(f"- {run.name}: {(summary or 'completed')[:120]}")
            if len(lines) >= 3:
                break
        if not lines:
            return self._fallback_answer(query=query)
        return "我已完成部分步骤，当前阶段结果：\n" + "\n".join(lines) + "\n如需我继续，我会基于这一步接着执行。"

    def _build_actions(self, runs: list[AgentLoopToolRun]) -> list[dict[str, str]]:
        return _build_actions_from_runs(
            runs=runs,
            user_id=int(getattr(self._tool_hub, "user_id", 0) or 0),
            workspace=str(self._tool_hub.workspace),
            resume_query=str(getattr(self, "_last_query", "") or ""),
            resume_request_json=str(getattr(self, "_resume_request_json", "") or ""),
        )
