from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.services.aelin_loop_logging import truncate_text
from app.services.aelin_loop_message import (
    build_screen_observation_message,
    prepare_tool_result_payload,
    safe_json_loads,
)
from app.services.aelin_loop_types import AgentLoopToolRun, AgentLoopTraceStep
from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage
from app.services.aelin_tools import AelinToolHub

_LOG = logging.getLogger(__name__)

_SENSITIVE_KEY_TOKENS = (
    "value",
    "password",
    "passwd",
    "passphrase",
    "token",
    "cookie",
    "authorization",
    "authheader",
    "auth_header",
    "secret",
    "apikey",
    "api_key",
    "credential",
    "sessionid",
    "session_id",
)
_MODEL_TOOL_RESULT_MAX_LEN = 1200
_MODEL_LIST_PREVIEW_ITEMS = 3
_MODEL_TEXT_PREVIEW_LEN = 220
def _normalized_key(key: str) -> str:
    return "".join(ch for ch in str(key or "").strip().lower() if ch.isalnum() or ch == "_")


def _is_sensitive_key(key: str) -> bool:
    norm = _normalized_key(key)
    if not norm:
        return False
    if norm in _SENSITIVE_KEY_TOKENS:
        return True
    return any(
        token in norm
        for token in ("password", "token", "secret", "cookie", "auth", "credential", "apikey", "api_key")
    )


def _redacted_marker(value: Any) -> str:
    if isinstance(value, str):
        return f"<redacted len={len(value)}>"
    if isinstance(value, list):
        return f"<redacted list len={len(value)}>"
    if isinstance(value, dict):
        return f"<redacted object keys={len(value)}>"
    return "<redacted>"


def _sanitize_for_log(value: Any, *, key_hint: str = "") -> Any:
    if key_hint and _is_sensitive_key(key_hint):
        return _redacted_marker(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return truncate_text(value, mask_data_image_url=True)
    if isinstance(value, list):
        items = [_sanitize_for_log(item) for item in value[:6]]
        if len(value) > 6:
            items.append("...truncated")
        return items
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for idx, (raw_key, raw_val) in enumerate(value.items()):
            if idx >= 8:
                out["..."] = "truncated"
                break
            key = str(raw_key or "")[:64]
            out[key] = _sanitize_for_log(raw_val, key_hint=key)
        return out
    return truncate_text(str(value), mask_data_image_url=True)


def _sanitize_tool_args_for_log(tool_name: str, args: dict[str, Any]) -> Any:
    return _sanitize_for_log(args)


def _dump_log_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "<json_encode_failed>"


def _summarize_result_for_log(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "ok": bool(result.get("ok", True)),
        "keys": [str(key)[:48] for key in list(result.keys())[:8]],
    }
    if result.get("error"):
        summary["error"] = _sanitize_for_log(result.get("error"))
    if result.get("message"):
        summary["message"] = _sanitize_for_log(result.get("message"))
    if result.get("scope"):
        summary["scope"] = _sanitize_for_log(result.get("scope"))
    if result.get("effect_summary"):
        summary["effect_summary"] = _sanitize_for_log(result.get("effect_summary"))
    return summary


def _truncate_model_text(value: Any, *, limit: int = _MODEL_TEXT_PREVIEW_LEN) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}…"


def _preview_item(item: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("title", "name", "url", "path", "snippet", "source", "provider", "id"):
        raw = item.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float, bool)):
            out[key] = raw
        else:
            out[key] = _truncate_model_text(raw, limit=180)
    return out


def _preview_browser_target(item: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("tag", "role", "text", "selector_hint", "name", "url"):
        raw = item.get(key)
        if raw is None:
            continue
        out[key] = _truncate_model_text(raw, limit=120)
    for key in ("x", "y"):
        raw = item.get(key)
        if isinstance(raw, (int, float)):
            out[key] = raw
    return out


def _compact_tool_result_for_model(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    tool = str(tool_name or "").strip().lower()
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_payload"}

    base: dict[str, Any] = {}
    for key in (
        "ok",
        "error",
        "action",
        "scope",
        "requires_confirmation",
        "confirm_kind",
        "risk_level",
        "effect_summary",
        "user_prompt",
        "hint",
    ):
        if key not in payload:
            continue
        val = payload.get(key)
        if isinstance(val, (bool, int, float)):
            base[key] = val
        else:
            base[key] = _truncate_model_text(val, limit=300)

    if tool == "screen_get":
        for key in ("name", "width", "height", "source_display", "captured_at", "has_image"):
            if key in payload:
                base[key] = payload.get(key)
        return base

    if tool == "web_search":
        base["query"] = _truncate_model_text(payload.get("query"), limit=220)
        base["total"] = int(payload.get("total") or 0)
        providers = payload.get("providers")
        if isinstance(providers, list):
            base["providers"] = [str(x)[:32] for x in providers[:_MODEL_LIST_PREVIEW_ITEMS]]
        items = payload.get("items")
        if isinstance(items, list):
            base["items"] = [
                _preview_item(row)
                for row in items[:_MODEL_LIST_PREVIEW_ITEMS]
                if isinstance(row, dict)
            ]
        return base

    if tool in {
        "context_get",
        "profile",
        "device",
        "plane",
        "skill",
        "pinchtab",
        "pinchtab_agent",
        "pinchtab_session",
    }:
        if tool == "skill":
            if "slug" in payload:
                base["slug"] = _truncate_model_text(payload.get("slug"), limit=64)
            if "summary" in payload:
                base["summary"] = _truncate_model_text(payload.get("summary"), limit=260)
            if "prompt" in payload:
                base["prompt_excerpt"] = _truncate_model_text(payload.get("prompt"), limit=800)
        if tool == "plane":
            if "plane" in payload:
                base["plane"] = _truncate_model_text(payload.get("plane"), limit=32)
            if "task_id" in payload:
                base["task_id"] = str(payload.get("task_id") or "")[:128]
            if "state" in payload:
                base["state"] = _truncate_model_text(payload.get("state"), limit=32)
            if isinstance(payload.get("last_text"), str):
                base["last_text"] = _truncate_model_text(payload.get("last_text"), limit=800)
            if isinstance(payload.get("last_url"), str):
                base["last_url"] = _truncate_model_text(payload.get("last_url"), limit=260)
            if isinstance(payload.get("user_prompt"), str):
                base["user_prompt"] = _truncate_model_text(payload.get("user_prompt"), limit=260)
        if tool in {"pinchtab", "pinchtab_agent", "pinchtab_session"}:
            # For PinchTab-family tools, preserve identifiers so the model can
            # chain calls across start/step/status and low-level operations.
            if "session_id" in payload:
                base["session_id"] = str(payload.get("session_id") or "")[:128]
            if "instance_id" in payload:
                base["instance_id"] = str(payload.get("instance_id") or "")[:128]
            if "tab_id" in payload:
                base["tab_id"] = str(payload.get("tab_id") or "")[:128]
            if "status" in payload:
                base["status"] = _truncate_model_text(payload.get("status"), limit=32)
            if "mode" in payload:
                base["mode"] = _truncate_model_text(payload.get("mode"), limit=32)
            # Expose browser content in a compact, model-friendly form so Aelin
            # can真正“看到” PinchTab 返回的页面信息，而不是只知道调用过工具。
            if tool in {"pinchtab_agent", "pinchtab_session"} and isinstance(payload.get("last_text"), str):
                base["last_text"] = _truncate_model_text(payload.get("last_text"), limit=800)
            # For low-level pinchtab.text responses, surface a short excerpt.
            if tool == "pinchtab" and isinstance(payload.get("text"), str):
                base["text_excerpt"] = _truncate_model_text(payload.get("text"), limit=800)
            # Common metadata from both primitive PinchTab calls and the agent/session wrappers.
            if isinstance(payload.get("url"), str):
                base["url"] = _truncate_model_text(payload.get("url"), limit=260)
            if isinstance(payload.get("last_url"), str):
                base["last_url"] = _truncate_model_text(payload.get("last_url"), limit=260)
            if isinstance(payload.get("title"), str):
                base["title"] = _truncate_model_text(payload.get("title"), limit=160)
            # Compact snapshot nodes when present so the model can reason about
            # what is on the page without flooding context.
            nodes = payload.get("nodes")
            if isinstance(nodes, list):
                base["nodes"] = [
                    _preview_browser_target(node)
                    for node in nodes[:_MODEL_LIST_PREVIEW_ITEMS]
                    if isinstance(node, dict)
                ]
            if "count" in payload:
                try:
                    base["count"] = int(payload.get("count") or 0)
                except Exception:
                    pass
            # For pinchtab_agent/session, also surface a compact view of executed
            # steps so the manager agent可以像人一样“看一眼进度”。
            if tool in {"pinchtab_agent", "pinchtab_session"} and isinstance(payload.get("steps"), list):
                compact_steps: list[dict[str, Any]] = []
                for step in list(payload.get("steps") or [])[:_MODEL_LIST_PREVIEW_ITEMS]:
                    if not isinstance(step, dict):
                        continue
                    s: dict[str, Any] = {}
                    for key in ("action", "status"):
                        if key in step:
                            s[key] = _truncate_model_text(step.get(key), limit=32)
                    for key in ("url", "ref"):
                        if key in step and isinstance(step.get(key), str):
                            s[key] = _truncate_model_text(step.get(key), limit=160)
                    if step.get("error"):
                        s["error"] = _truncate_model_text(step.get("error"), limit=80)
                    if s:
                        compact_steps.append(s)
                if compact_steps:
                    base["steps"] = compact_steps
        if "summary" in payload:
            base["summary"] = _truncate_model_text(payload.get("summary"), limit=260)
        if "total" in payload:
            base["total"] = int(payload.get("total") or 0)
        if "next_call" in payload and isinstance(payload.get("next_call"), dict):
            # For PinchTab-family tools we want the model to see the raw
            # next_call (including identifiers like session_id / instance_id)
            # so it can faithfully continue the same session. Logging is still
            # sanitized separately via _sanitize_for_log in the logging path.
            if tool in {"pinchtab", "pinchtab_agent", "pinchtab_session"}:
                base["next_call"] = payload.get("next_call")
            else:
                base["next_call"] = _sanitize_for_log(payload.get("next_call"))
        items = payload.get("items")
        if isinstance(items, list):
            base["items"] = [
                _preview_item(row)
                for row in items[:_MODEL_LIST_PREVIEW_ITEMS]
                if isinstance(row, dict)
            ]
        if "focus_items" in payload and isinstance(payload.get("focus_items"), list):
            base["focus_items"] = [
                _preview_item(row)
                for row in list(payload.get("focus_items") or [])[:_MODEL_LIST_PREVIEW_ITEMS]
                if isinstance(row, dict)
            ]
        if "todos" in payload and isinstance(payload.get("todos"), list):
            base["todos"] = [
                _preview_item(row)
                for row in list(payload.get("todos") or [])[:_MODEL_LIST_PREVIEW_ITEMS]
                if isinstance(row, dict)
            ]
        return base

    if "next_call" in payload and isinstance(payload.get("next_call"), dict):
        # Same rule as above: do not redact identifiers for PinchTab-family
        # tools when sending results to the model. This keeps the model-visible
        # plan faithful, while logs remain sanitized.
        if tool in {"pinchtab", "pinchtab_agent", "pinchtab_session"}:
            base["next_call"] = payload.get("next_call")
        else:
            base["next_call"] = _sanitize_for_log(payload.get("next_call"))
    if "items" in payload and isinstance(payload.get("items"), list):
        base["items"] = [
            _preview_item(row)
            for row in list(payload.get("items") or [])[:_MODEL_LIST_PREVIEW_ITEMS]
            if isinstance(row, dict)
        ]
    if len(base) <= 1:
        base["preview"] = _truncate_model_text(_sanitize_for_log(payload), limit=600)
    return base


def _serialize_tool_message_content(payload: dict[str, Any], *, max_len: int = _MODEL_TOOL_RESULT_MAX_LEN) -> str:
    raw = json.dumps(payload, ensure_ascii=False)
    if len(raw) <= max_len:
        return raw
    preview = raw[: min(1000, max_len)]
    compact: dict[str, Any] = {
        "truncated": True,
        "original_length": len(raw),
        "preview": preview,
    }
    if "ok" in payload:
        compact["ok"] = bool(payload.get("ok"))
    return json.dumps(compact, ensure_ascii=False)


def build_tool_calls_payload(raw_tool_calls: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in raw_tool_calls:
        # Provider原生 tool_calls 通常是具有 .id / .function.name / .function.arguments
        # 属性的对象；而适配层可能会构造一个等价的 dict 结构。
        if isinstance(tc, dict):
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            out.append(
                {
                    "id": str(tc.get("id") or ""),
                    "type": str(tc.get("type") or "function") or "function",
                    "function": {
                        "name": str(fn.get("name") or "").strip(),
                        "arguments": str(fn.get("arguments") or "{}") or "{}",
                    },
                }
            )
            continue

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
    safe_tool_name = str(tool_name or "").strip().lower()
    _LOG.info(
        "agent_loop tool_call_start tool=%s args=%s",
        safe_tool_name,
        _dump_log_json(_sanitize_tool_args_for_log(safe_tool_name, args or {})),
    )
    started = time.perf_counter()
    try:
        result = tool_hub.execute(safe_tool_name, args or {})
        if not bool(result.get("ok", True)):
            status = "failed"
            error = str(result.get("error") or "tool_not_ok")[:180]
    except Exception as exc:
        status = "failed"
        error = str(exc)[:180]
        result = {"ok": False, "error": error}
    latency_ms = int((time.perf_counter() - started) * 1000)
    _LOG.info(
        "agent_loop tool_call_end tool=%s status=%s latency_ms=%s result=%s",
        safe_tool_name,
        status,
        latency_ms,
        _dump_log_json(_summarize_result_for_log(result)),
    )
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
    compact_message_result = _compact_tool_result_for_model(tool_name, tool_result_for_message)
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
            "content": _serialize_tool_message_content(compact_message_result),
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
        for future in as_completed(future_map):
            idx = future_map[future]
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
