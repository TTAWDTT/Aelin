from __future__ import annotations

import json
import logging
import time
import hashlib
import threading
from collections.abc import Callable
from typing import Any

from app.services.aelin_loop_actions import build_actions as _build_actions_from_runs
from app.services.aelin_loop_logging import safe_preview
from app.services.aelin_loop_message import build_initial_messages, extract_message_text
from app.services.aelin_loop_round import request_round_response
from app.services.aelin_loop_tools import (
    _compact_tool_result_for_model,
    _sanitize_tool_args_for_log,
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
_SERIAL_READ_TOOLS: set[str] = set()


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


def _json_compact(value: Any, *, limit: int = 220) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        text = str(value or "")
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(0, limit - 1)]}…"


def _tool_result_summary(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return _json_compact(result, limit=180)
    for key in ("effect_summary", "summary", "message", "error", "hint"):
        value = str(result.get(key) or "").strip()
        if value:
            return _json_compact(value, limit=180)
    keys = [str(k) for k in list(result.keys())[:6]]
    return _json_compact({"ok": bool(result.get("ok", True)), "keys": keys}, limit=180)


def _emit_text_chunks(text: str, callback: Callable[[str], None] | None, *, chunk_size: int = 48) -> None:
    if callback is None:
        return
    raw = str(text or "")
    if not raw:
        return
    size = max(8, min(120, int(chunk_size or 48)))
    for idx in range(0, len(raw), size):
        piece = raw[idx : idx + size]
        if not piece:
            continue
        try:
            callback(piece)
        except Exception:
            break


def _split_tool_partial_messages(summary: str, *, max_part_len: int = 80) -> list[str]:
    text = " ".join(str(summary or "").split())
    if not text:
        return []
    segments: list[str] = []
    cursor = 0
    size = max(24, min(120, int(max_part_len or 80)))
    while cursor < len(text):
        remaining = text[cursor : cursor + size]
        if len(remaining) < size:
            segments.append(remaining)
            break
        split_idx = max(remaining.rfind("，"), remaining.rfind(","), remaining.rfind("。"), remaining.rfind(";"))
        if split_idx < 24:
            split_idx = size
        part = text[cursor : cursor + split_idx].strip()
        if part:
            segments.append(part)
        cursor += max(1, split_idx)
    return segments[:6]


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
        round_max_tokens: int = 320,
        final_max_tokens: int = 320,
    ) -> None:
        self._service = service
        self._provider = str(provider or "").strip().lower()
        self._tool_hub = tool_hub
        self._policy = policy
        self._max_rounds = max(1, int(max_rounds or 1))
        self._round_timeout_seconds = max(2.0, float(round_timeout_seconds or 10.0))
        self._total_timeout_seconds = max(3.0, float(total_timeout_seconds or 12.0))
        self._round_max_tokens = max(220, int(round_max_tokens or 320))
        self._final_max_tokens = max(320, int(final_max_tokens or 320))

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
        trace_cb: Callable[[AgentLoopTraceStep], None] | None = None,
        reply_chunk_cb: Callable[[str], None] | None = None,
        tool_event_cb: Callable[[dict[str, Any]], None] | None = None,
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
        tool_partial_seen: dict[str, int] = {}
        tool_event_emit_lock = threading.Lock()

        def _emit_trace_step(step: AgentLoopTraceStep) -> None:
            trace_steps.append(step)
            if trace_cb is not None:
                try:
                    trace_cb(step)
                except Exception:
                    pass

        def _emit_trace_only(step: AgentLoopTraceStep) -> None:
            if trace_cb is not None:
                try:
                    trace_cb(step)
                except Exception:
                    pass

        def _emit_trace(*, stage: str, status: str, detail: str = "", count: int = 0) -> None:
            _emit_trace_step(
                AgentLoopTraceStep(
                    stage=str(stage or "agent_loop")[:80],
                    status=str(status or "completed")[:24],
                    detail=str(detail or "")[:240],
                    count=max(0, int(count or 0)),
                )
            )

        def _tool_stage(round_index: int, tool_name: str, tc_id: str) -> str:
            safe_tool = str(tool_name or "tool").strip().lower()[:24] or "tool"
            base_key = f"{round_index}:{safe_tool}:{tc_id}"
            digest = hashlib.sha1(base_key.encode("utf-8", errors="ignore")).hexdigest()[:8]
            return f"tool_call:{safe_tool}:{digest}"

        def _forward_tool_event(payload: dict[str, Any]) -> None:
            with tool_event_emit_lock:
                raw_tool_name = str(payload.get("tool_name") or "tool").strip().lower()
                raw_args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
                safe_args = (
                    _sanitize_tool_args_for_log(raw_tool_name, raw_args)
                    if isinstance(raw_args, dict)
                    else {}
                )
                safe_payload = dict(payload)
                safe_payload["tool_name"] = raw_tool_name
                safe_payload["args"] = safe_args
                if tool_event_cb is not None:
                    try:
                        tool_event_cb(safe_payload)
                    except Exception:
                        pass
                phase = str(safe_payload.get("phase") or "").strip().lower()
                round_no = max(1, int(safe_payload.get("round_index") or 1))
                tool_name = raw_tool_name
                tc_id = str(safe_payload.get("tc_id") or "")
                args = safe_args if isinstance(safe_args, dict) else {}
                stage = str(safe_payload.get("stage") or "").strip() or _tool_stage(round_no, tool_name, tc_id)
                if phase == "start":
                    tool_partial_seen[stage] = 0
                    _emit_trace(
                        stage=stage,
                        status="running",
                        detail=f"round={round_no}; tool={tool_name}; args={_json_compact(args, limit=160)}",
                        count=0,
                    )
                    return
                if phase == "partial":
                    message = str(safe_payload.get("message") or safe_payload.get("summary") or safe_payload.get("progress") or "").strip()
                    current_action = str(safe_payload.get("current_action") or "").strip()
                    progress_label = str(safe_payload.get("progress_label") or "").strip()
                    tick = max(0, int(safe_payload.get("tick") or 0))
                    elapsed_ms = max(0, int(safe_payload.get("elapsed_ms") or 0))
                    found_count = max(0, int(safe_payload.get("found_count") or 0))
                    processed = max(0, int(safe_payload.get("processed") or 0))
                    matched = max(0, int(safe_payload.get("matched") or 0))
                    total = max(0, int(safe_payload.get("total") or 0))
                    if message or current_action or progress_label:
                        tool_partial_seen[stage] = max(0, int(tool_partial_seen.get(stage, 0))) + 1
                        detail_parts = [f"round={round_no}", f"tool={tool_name}"]
                        if current_action:
                            detail_parts.append(f"current_action={_json_compact(current_action, limit=120)}")
                        if progress_label:
                            detail_parts.append(f"progress_label={progress_label}")
                        if tick > 0:
                            detail_parts.append(f"tick={tick}")
                        if found_count > 0:
                            detail_parts.append(f"found_count={found_count}")
                        if processed > 0:
                            detail_parts.append(f"processed={processed}")
                        if matched > 0:
                            detail_parts.append(f"matched={matched}")
                        if total > 0:
                            detail_parts.append(f"total={total}")
                        if elapsed_ms > 0:
                            detail_parts.append(f"elapsed_ms={elapsed_ms}")
                        if message:
                            detail_parts.append(f"partial={_json_compact(message, limit=140)}")
                        _emit_trace(
                            stage=stage,
                            status="running",
                            detail="; ".join(detail_parts),
                            count=0,
                        )
                    return
                if phase == "end":
                    result_payload = safe_payload.get("result") if isinstance(safe_payload.get("result"), dict) else {}
                    status_raw = str(safe_payload.get("status") or "").strip().lower()
                    status_norm = "completed" if status_raw == "completed" else "failed"
                    latency_ms = max(0, int(safe_payload.get("latency_ms") or 0))
                    summary_text = _tool_result_summary(result_payload)
                    if status_norm == "completed" and int(tool_partial_seen.get(stage, 0) or 0) <= 0:
                        for partial in _split_tool_partial_messages(summary_text):
                            partial_payload = {
                                "phase": "partial",
                                "round_index": round_no,
                                "tool_name": tool_name,
                                "tc_id": tc_id,
                                "args": args,
                                "message": partial,
                                "stage": stage,
                            }
                            if tool_event_cb is not None:
                                try:
                                    tool_event_cb(partial_payload)
                                except Exception:
                                    pass
                    _emit_trace(
                        stage=stage,
                        status=status_norm,
                        detail=(
                            f"round={round_no}; tool={tool_name}; latency_ms={latency_ms}; "
                            f"summary={summary_text}"
                        ),
                        count=1 if status_norm == "completed" else 0,
                    )
                    return
                if phase == "blocked":
                    reason = str(safe_payload.get("reason") or "policy_denied").strip()
                    _emit_trace(
                        stage=stage,
                        status="failed",
                        detail=f"round={round_no}; tool={tool_name}; blocked={reason}",
                        count=0,
                    )

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
        _emit_trace(stage="agent_loop", status="running", detail="start", count=0)

        loop_started = time.perf_counter()
        idle_rounds = 0
        for round_index in range(1, self._max_rounds + 1):
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                stop_reason = "client_disconnected"
                _emit_trace_step(
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
                _emit_trace(
                    stage="agent_loop_round",
                    status="failed",
                    detail=f"total_timeout={self._total_timeout_seconds:.1f}s",
                    count=0,
                )
                break

            rounds = round_index
            usage.round_calls = 0
            _emit_trace(stage="agent_loop_round", status="running", detail=f"round={round_index}", count=0)
            response, retried_without_images, llm_error_reason = request_round_response(
                client=client,
                service=self._service,
                messages=messages,
                tools=tools,
                round_timeout_seconds=self._round_timeout_seconds,
                round_max_tokens=self._round_max_tokens,
                round_index=round_index,
                trace_steps=trace_steps,
                retried_without_images=retried_without_images,
                trace_emit_cb=_emit_trace_only,
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
                _emit_trace(
                    stage="agent_loop_round",
                    status="completed" if answer else "failed",
                    detail=f"round={round_index}; stop={stop_reason}",
                    count=0,
                )
                _emit_text_chunks(answer, reply_chunk_cb, chunk_size=48)
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
            _emit_trace(
                stage="tool_scheduler",
                status="completed" if planned_calls else "skipped",
                detail=f"round={round_index}; planned_calls={len(planned_calls)}; reached_limit={1 if reached_total_limit else 0}",
                count=len(planned_calls),
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
                            tool_event_cb=_forward_tool_event,
                            trace_emit_cb=_emit_trace_only,
                        )
                        call_stage = _tool_stage(round_index, tool_name, tc_id)
                        _forward_tool_event(
                            {
                                "phase": "start",
                                "round_index": round_index,
                                "tool_name": tool_name,
                                "tc_id": tc_id,
                                "args": args,
                                "stage": call_stage,
                            }
                        )
                        status, result, error, latency_ms = execute_tool_call(
                            tool_hub=self._tool_hub,
                            tool_name=tool_name,
                            args=args,
                            partial_cb=lambda partial_state, *, _round=round_index, _tool=tool_name, _tc=tc_id, _args=args, _stage=call_stage: _forward_tool_event(
                                {
                                    "phase": "partial",
                                    "round_index": _round,
                                    "tool_name": _tool,
                                    "tc_id": _tc,
                                    "args": _args,
                                    "stage": _stage,
                                    **(partial_state if isinstance(partial_state, dict) else {}),
                                }
                            ),
                        )
                        _forward_tool_event(
                            {
                                "phase": "end",
                                "round_index": round_index,
                                "tool_name": tool_name,
                                "tc_id": tc_id,
                                "args": args,
                                "status": status,
                                "result": result,
                                "error": error,
                                "latency_ms": latency_ms,
                                "stage": call_stage,
                            }
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
                            trace_emit_cb=_emit_trace_only,
                        ):
                            successful_calls += 1
                        if pending_confirmation is None:
                            pending_confirmation = _extract_confirmation_request(
                                tool_name=tool_name,
                                args=args,
                                result=result,
                                query=query,
                            )
                        continue
                    pending_reads.append(
                        {
                            **planned,
                            "stage": _tool_stage(round_index, tool_name, tc_id),
                        }
                    )
                    continue

                successful_calls += flush_pending_reads(
                    pending_reads=pending_reads,
                    tool_hub=self._tool_hub,
                    round_index=round_index,
                    messages=messages,
                    tool_runs=tool_runs,
                    trace_steps=trace_steps,
                    tool_event_cb=_forward_tool_event,
                    trace_emit_cb=_emit_trace_only,
                )
                if not allowed:
                    call_stage = _tool_stage(round_index, tool_name, tc_id)
                    _forward_tool_event(
                        {
                            "phase": "start",
                            "round_index": round_index,
                            "tool_name": tool_name,
                            "tc_id": tc_id,
                            "args": args,
                            "stage": call_stage,
                        }
                    )
                    _forward_tool_event(
                        {
                            "phase": "blocked",
                            "round_index": round_index,
                            "tool_name": tool_name,
                            "tc_id": tc_id,
                            "args": args,
                            "reason": f"policy:{reason}",
                            "stage": call_stage,
                        }
                    )
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
                        trace_emit_cb=_emit_trace_only,
                    ):
                        successful_calls += 1
                    continue

                call_stage = _tool_stage(round_index, tool_name, tc_id)
                _forward_tool_event(
                    {
                        "phase": "start",
                        "round_index": round_index,
                        "tool_name": tool_name,
                        "tc_id": tc_id,
                        "args": args,
                        "stage": call_stage,
                    }
                )
                status, result, error, latency_ms = execute_tool_call(
                    tool_hub=self._tool_hub,
                    tool_name=tool_name,
                    args=args,
                    partial_cb=lambda partial_state, *, _round=round_index, _tool=tool_name, _tc=tc_id, _args=args, _stage=call_stage: _forward_tool_event(
                        {
                            "phase": "partial",
                            "round_index": _round,
                            "tool_name": _tool,
                            "tc_id": _tc,
                            "args": _args,
                            "stage": _stage,
                            **(partial_state if isinstance(partial_state, dict) else {}),
                        }
                    ),
                )
                _forward_tool_event(
                    {
                        "phase": "end",
                        "round_index": round_index,
                        "tool_name": tool_name,
                        "tc_id": tc_id,
                        "args": args,
                        "status": status,
                        "result": _compact_tool_result_for_model(
                            tool_name,
                            result if isinstance(result, dict) else {},
                        ),
                        "error": error,
                        "latency_ms": latency_ms,
                        "stage": call_stage,
                    }
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
                    trace_emit_cb=_emit_trace_only,
                ):
                    successful_calls += 1
                if pending_confirmation is None:
                    pending_confirmation = _extract_confirmation_request(
                        tool_name=tool_name,
                        args=args,
                        result=result,
                        query=query,
                    )

            if pending_confirmation is not None:
                stop_reason = "requires_confirmation"
                _emit_trace(
                    stage="agent_loop_confirm",
                    status="completed",
                    detail=f"tool={pending_confirmation.get('tool')}; kind={pending_confirmation.get('confirm_kind') or '-'}",
                    count=1,
                )
                break
            successful_calls += flush_pending_reads(
                pending_reads=pending_reads,
                tool_hub=self._tool_hub,
                round_index=round_index,
                messages=messages,
                tool_runs=tool_runs,
                trace_steps=trace_steps,
                tool_event_cb=_forward_tool_event,
                trace_emit_cb=_emit_trace_only,
            )

            if successful_calls <= 0:
                idle_rounds += 1
            else:
                idle_rounds = 0
            _emit_trace(
                stage="agent_loop_round",
                status="completed",
                detail=f"round={round_index}; calls={usage.round_calls}; successful={successful_calls}",
                count=usage.round_calls,
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
            if pending_confirmation is not None:
                answer = str(pending_confirmation.get("user_prompt") or "").strip()
                stop_reason = "requires_confirmation"
            elif stop_reason == "total_timeout":
                answer = "我已达到本轮时限，先返回阶段性结论。你可以缩小问题范围后我继续执行。"
            elif usage.total_calls > 0 and stop_reason in {"total_call_limit", "no_progress", "max_rounds"}:
                synthesized = self._final_answer(
                    messages,
                    query=query,
                    reply_chunk_cb=reply_chunk_cb,
                    fallback_on_error=False,
                )
                if synthesized:
                    answer = synthesized
                    stop_reason = "finalized_after_tools"
                else:
                    answer = self._partial_answer_from_runs(tool_runs=tool_runs, query=query)
                    stop_reason = "partial_result"
                    _emit_text_chunks(answer, reply_chunk_cb, chunk_size=64)
            else:
                answer = self._final_answer(messages, query=query, reply_chunk_cb=reply_chunk_cb)
                if answer and stop_reason == "empty_answer":
                    stop_reason = "finalized_after_tools"

        actions = self._build_actions(tool_runs)
        _emit_trace(
            stage="agent_loop",
            status="completed" if answer else "failed",
            detail=f"stop={stop_reason}; rounds={rounds}; calls={usage.total_calls}",
            count=usage.total_calls,
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

    def _final_answer(
        self,
        messages: list[dict[str, Any]],
        *,
        query: str,
        reply_chunk_cb: Callable[[str], None] | None = None,
        fallback_on_error: bool = True,
    ) -> str:
        try:
            final_messages = list(messages)
            final_messages.append(
                {
                    "role": "user",
                    "content": "请基于已完成的工具结果，直接给出最终中文回答。不要继续调用工具。",
                }
            )
            _LOG.info("agent_loop final_answer_request messages=%s", len(final_messages))
            stream_text_parts: list[str] = []
            try:
                stream_resp = self._service.client.chat.completions.create(
                    model=self._service.config.model,
                    messages=final_messages,
                    temperature=self._service.config.temperature,
                    max_tokens=self._final_max_tokens,
                    timeout=self._round_timeout_seconds,
                    stream=True,
                )
                for chunk in stream_resp:
                    choice = chunk.choices[0] if getattr(chunk, "choices", None) else None
                    delta = getattr(choice, "delta", None) if choice else None
                    piece = extract_message_text(getattr(delta, "content", ""))
                    if not piece:
                        continue
                    stream_text_parts.append(piece)
                    if reply_chunk_cb is not None:
                        try:
                            reply_chunk_cb(piece)
                        except Exception:
                            pass
                stream_text = "".join(stream_text_parts).strip()
                if stream_text:
                    _LOG.info("agent_loop final_answer_response text=%s", safe_preview(stream_text))
                    return stream_text
            except Exception as stream_exc:
                _LOG.warning("agent_loop final_answer_stream_failed error=%s", str(stream_exc)[:200])

            response = self._service.client.chat.completions.create(
                model=self._service.config.model,
                messages=final_messages,
                temperature=self._service.config.temperature,
                max_tokens=self._final_max_tokens,
                timeout=self._round_timeout_seconds,
            )
            choice = response.choices[0] if getattr(response, "choices", None) else None
            message = getattr(choice, "message", None) if choice else None
            text_out = extract_message_text(getattr(message, "content", ""))
            if text_out:
                _LOG.info("agent_loop final_answer_response text=%s", safe_preview(text_out))
                _emit_text_chunks(text_out, reply_chunk_cb, chunk_size=64)
                return text_out
        except Exception as exc:
            _LOG.warning("agent_loop final_answer_failed error=%s", str(exc)[:200])
        if not fallback_on_error:
            return ""
        fallback = self._fallback_answer(query=query)
        _emit_text_chunks(fallback, reply_chunk_cb, chunk_size=64)
        return fallback

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
