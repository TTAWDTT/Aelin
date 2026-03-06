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
_BROWSER_AMBIGUOUS_CLICK_TARGETS = {
    "window",
    "browser window",
    "浏览器窗口",
    "窗口",
    "当前窗口",
    "window focus",
    "个人资料头像或profile链接",
    "profile链接",
}


@dataclass
class _BrowserLoopState:
    preferred_scope: str = ""
    last_observed_url: str = ""
    last_requested_navigate_url: str = ""
    last_dom_url: str = ""
    consecutive_same_navigate_count: int = 0


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
    safe_tool = str(tool_name or "").strip().lower()
    action = str(args.get("action") or "").strip().lower()
    if safe_tool == "browser_use" and action == "type":
        return {
            "action": action,
            "scope": _sanitize_for_log(args.get("scope")),
            "strategy": _sanitize_for_log(args.get("strategy")),
            "confirm": bool(args.get("confirm", False)),
            "sensitive_args": True,
        }
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


def _browser_loop_state(tool_hub: AelinToolHub) -> _BrowserLoopState:
    state = getattr(tool_hub, "_browser_loop_state", None)
    if isinstance(state, _BrowserLoopState):
        return state
    state = _BrowserLoopState()
    setattr(tool_hub, "_browser_loop_state", state)
    return state


def _normalize_browser_url(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.rstrip("/")


def _is_ambiguous_browser_click_target(raw: Any) -> bool:
    target = " ".join(str(raw or "").strip().lower().split())
    if not target:
        return True
    if target in _BROWSER_AMBIGUOUS_CLICK_TARGETS:
        return True
    if "头像" in target and "profile" in target:
        return True
    return False


def _has_browser_click_locator(args: dict[str, Any]) -> bool:
    if not isinstance(args, dict):
        return False
    for key in ("selector", "role", "text", "xpath"):
        value = args.get(key)
        if str(value or "").strip():
            return True
    return False


def _browser_short_circuit_result(*, action: str, scope: str, effect_summary: str, url: str) -> dict[str, Any]:
    normalized_url = _normalize_browser_url(url)
    return {
        "ok": True,
        "action": action,
        "scope": scope or "cdp",
        "effect_summary": effect_summary,
        "requires_confirmation": False,
        "risk_level": "low",
        "external_opened": False,
        "before": {"url": normalized_url, "title": ""},
        "after": {"url": normalized_url, "title": ""},
        "session_id": "",
    }


def _optimize_browser_tool_call(
    *,
    tool_hub: AelinToolHub,
    tool_name: str,
    args: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    safe_tool = str(tool_name or "").strip().lower()
    if safe_tool not in {"browser_use", "browser_state_get"}:
        return args, None

    state = _browser_loop_state(tool_hub)
    rewritten = dict(args or {})

    if safe_tool == "browser_state_get":
        requested_scope = str(rewritten.get("scope") or "auto").strip().lower()
        include_dom = bool(rewritten.get("include_dom", False))
        include_a11y = bool(rewritten.get("include_a11y", False))
        if state.preferred_scope == "cdp" and requested_scope in {"", "auto", "external"}:
            rewritten["scope"] = "cdp"
        if include_a11y and not include_dom and (state.preferred_scope == "cdp" or state.last_observed_url):
            rewritten["include_dom"] = True
        return rewritten, None

    action = str(rewritten.get("action") or "").strip().lower()
    requested_scope = str(rewritten.get("scope") or "auto").strip().lower()
    if state.preferred_scope == "cdp" and requested_scope in {"", "auto", "external"}:
        rewritten["scope"] = "cdp"

    if action == "navigate":
        target_url = _normalize_browser_url(rewritten.get("url"))
        if target_url and target_url == state.last_observed_url:
            return rewritten, _browser_short_circuit_result(
                action="navigate",
                scope=str(rewritten.get("scope") or state.preferred_scope or "cdp"),
                effect_summary=f"already_at:{target_url}",
                url=target_url,
            )
        return rewritten, None

    if action == "click" and not _has_browser_click_locator(rewritten) and _is_ambiguous_browser_click_target(
        rewritten.get("target")
    ):
        return rewritten, {
            "ok": False,
            "error": "ambiguous_browser_target",
            "action": "click",
            "hint": "目标过于模糊。请先读取 DOM，再基于可见文本、selector 或 role 发起点击。",
        }
    return rewritten, None


def _record_browser_tool_result(
    *,
    tool_hub: AelinToolHub,
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any],
) -> None:
    safe_tool = str(tool_name or "").strip().lower()
    if safe_tool not in {"browser_use", "browser_state_get"}:
        return
    if not isinstance(result, dict):
        return
    state = _browser_loop_state(tool_hub)
    scope = str(result.get("scope") or args.get("scope") or "").strip().lower()
    if scope == "cdp":
        state.preferred_scope = "cdp"
    elif scope == "external" and not state.preferred_scope:
        state.preferred_scope = "external"

    if safe_tool == "browser_state_get":
        observed_url = _normalize_browser_url(result.get("url"))
        if observed_url:
            state.last_observed_url = observed_url
        include_dom = bool(args.get("include_dom", False))
        if include_dom and observed_url:
            state.last_dom_url = observed_url
        return

    action = str(args.get("action") or result.get("action") or "").strip().lower()
    if action != "navigate":
        return
    if not bool(result.get("ok", False)):
        return
    target_url = _normalize_browser_url(args.get("url"))
    if target_url:
        if target_url == state.last_requested_navigate_url:
            state.consecutive_same_navigate_count += 1
        else:
            state.last_requested_navigate_url = target_url
            state.consecutive_same_navigate_count = 1
    observed_after = result.get("after") if isinstance(result.get("after"), dict) else {}
    observed_url = _normalize_browser_url(observed_after.get("url"))
    if observed_url:
        state.last_observed_url = observed_url


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

    if tool in {"context_get", "browser_state_get", "browser_session_list", "tracking", "diary", "profile", "device"}:
        if "summary" in payload:
            base["summary"] = _truncate_model_text(payload.get("summary"), limit=260)
        if "url" in payload:
            base["url"] = _truncate_model_text(payload.get("url"), limit=240)
        if "title" in payload:
            base["title"] = _truncate_model_text(payload.get("title"), limit=200)
        if "total" in payload:
            base["total"] = int(payload.get("total") or 0)
        if "next_call" in payload and isinstance(payload.get("next_call"), dict):
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
        if "system_processes" in payload and isinstance(payload.get("system_processes"), list):
            base["system_processes"] = [
                _preview_item(row)
                for row in list(payload.get("system_processes") or [])[:_MODEL_LIST_PREVIEW_ITEMS]
                if isinstance(row, dict)
            ]
        return base

    if "next_call" in payload and isinstance(payload.get("next_call"), dict):
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
    effective_args, synthetic_result = _optimize_browser_tool_call(
        tool_hub=tool_hub,
        tool_name=safe_tool_name,
        args=args,
    )
    _LOG.info(
        "agent_loop tool_call_start tool=%s args=%s",
        safe_tool_name,
        _dump_log_json(_sanitize_tool_args_for_log(safe_tool_name, effective_args)),
    )
    started = time.perf_counter()
    try:
        if isinstance(synthetic_result, dict):
            result = dict(synthetic_result)
        else:
            result = tool_hub.execute(safe_tool_name, effective_args)
        if not bool(result.get("ok", True)):
            status = "failed"
            error = str(result.get("error") or "tool_not_ok")[:180]
    except Exception as exc:
        status = "failed"
        error = str(exc)[:180]
        result = {"ok": False, "error": error}
    latency_ms = int((time.perf_counter() - started) * 1000)
    _record_browser_tool_result(
        tool_hub=tool_hub,
        tool_name=safe_tool_name,
        args=effective_args,
        result=result,
    )
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
