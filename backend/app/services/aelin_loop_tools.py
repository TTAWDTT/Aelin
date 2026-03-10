from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
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
_TOOL_PARTIAL_INTERVAL_MS = 180
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


def _tool_partial_state(tool_name: str, args: dict[str, Any], tick: int, *, elapsed_ms: int = 0) -> dict[str, Any]:
    safe_tool = str(tool_name or "").strip().lower()
    tick_index = max(0, int(tick or 0))
    step = tick_index + 1
    cycle = tick_index % 3
    if safe_tool in {"attachment_search", "file_memory_search", "local_search"}:
        if cycle == 0:
            return {
                "message": f"正在检索附件内容（第{step}轮）...",
                "current_action": "正在检索附件内容",
                "progress_label": "searching",
                "tick": step,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
            }
        if cycle == 1:
            return {
                "message": f"已找到第{step}条候选片段...",
                "current_action": "已找到候选片段",
                "progress_label": "found_candidates",
                "tick": step,
                "found_count": step,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
            }
        return {
            "message": f"正在整理检索结果（第{step}轮）...",
            "current_action": "正在整理检索结果",
            "progress_label": "organizing",
            "tick": step,
            "elapsed_ms": max(0, int(elapsed_ms or 0)),
        }
    if safe_tool in {"web_search"}:
        if cycle == 0:
            return {
                "message": f"正在检索网页内容（第{step}轮）...",
                "current_action": "正在检索网页内容",
                "progress_label": "searching_web",
                "tick": step,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
            }
        if cycle == 1:
            return {
                "message": f"已抓取第{step}条候选结果...",
                "current_action": "已抓取候选结果",
                "progress_label": "fetched_candidates",
                "tick": step,
                "found_count": step,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
            }
        return {
            "message": f"正在整理网页检索结果（第{step}轮）...",
            "current_action": "正在整理网页检索结果",
            "progress_label": "organizing_web",
            "tick": step,
            "elapsed_ms": max(0, int(elapsed_ms or 0)),
        }
    if safe_tool in {"attachment_prefetch"}:
        if cycle == 0:
            return {
                "message": f"正在解析附件（第{step}轮）...",
                "current_action": "正在解析附件",
                "progress_label": "parsing",
                "tick": step,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
            }
        if cycle == 1:
            return {
                "message": f"正在切分内容并建立索引（第{step}轮）...",
                "current_action": "正在切分内容并建立索引",
                "progress_label": "indexing",
                "tick": step,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
            }
        return {
            "message": f"正在写入检索缓存（第{step}轮）...",
            "current_action": "正在写入检索缓存",
            "progress_label": "caching",
            "tick": step,
            "elapsed_ms": max(0, int(elapsed_ms or 0)),
        }
    if safe_tool in {"browser_use", "browser_state_get"}:
        action = str(args.get("action") or "").strip().lower()
        if action:
            return {
                "message": f"正在执行浏览器动作：{action}...",
                "current_action": f"正在执行浏览器动作：{action}",
                "progress_label": "browser_action",
                "tick": step,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
            }
        return {
            "message": "正在执行浏览器动作...",
            "current_action": "正在执行浏览器动作",
            "progress_label": "browser_action",
            "tick": step,
            "elapsed_ms": max(0, int(elapsed_ms or 0)),
        }
    if safe_tool in {"code_write"}:
        if cycle == 0:
            return {
                "message": f"正在生成代码变更（第{step}轮）...",
                "current_action": "正在生成代码变更",
                "progress_label": "planning_code",
                "tick": step,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
            }
        if cycle == 1:
            return {
                "message": f"正在执行代码任务（第{step}轮）...",
                "current_action": "正在执行代码任务",
                "progress_label": "executing_code",
                "tick": step,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
            }
        return {
            "message": f"正在整理代码执行结果（第{step}轮）...",
            "current_action": "正在整理代码执行结果",
            "progress_label": "organizing_code",
            "tick": step,
            "elapsed_ms": max(0, int(elapsed_ms or 0)),
        }
    return {
        "message": f"正在执行工具调用（第{step}轮）...",
        "current_action": "正在执行工具调用",
        "progress_label": "running_tool",
        "tick": step,
        "elapsed_ms": max(0, int(elapsed_ms or 0)),
    }


def _progress_sensitive_tool(tool_name: str) -> bool:
    safe_tool = str(tool_name or "").strip().lower()
    return safe_tool in {
        "attachment_prefetch",
        "attachment_search",
        "file_memory_search",
        "local_search",
        "web_search",
    }


def _structured_progress_tool(tool_name: str) -> bool:
    safe_tool = str(tool_name or "").strip().lower()
    return safe_tool in {"attachment_search"}


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
        if state.preferred_scope == "cdp" and requested_scope in {"", "auto"}:
            rewritten["scope"] = "cdp"
        if include_a11y and not include_dom and (state.preferred_scope == "cdp" or state.last_observed_url):
            rewritten["include_dom"] = True
        return rewritten, None

    action = str(rewritten.get("action") or "").strip().lower()
    requested_scope = str(rewritten.get("scope") or "auto").strip().lower()
    if state.preferred_scope == "cdp" and requested_scope in {"", "auto"}:
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

    if tool in {"context_get", "browser_state_get", "browser_session_list", "tracking", "diary", "profile", "device"}:
        browser_state_payload = payload
        if tool == "browser_state_get" and isinstance(payload.get("active_state"), dict):
            browser_state_payload = payload.get("active_state") or payload
        if "summary" in payload:
            base["summary"] = _truncate_model_text(payload.get("summary"), limit=260)
        if "url" in browser_state_payload:
            base["url"] = _truncate_model_text(browser_state_payload.get("url"), limit=240)
        if "title" in browser_state_payload:
            base["title"] = _truncate_model_text(browser_state_payload.get("title"), limit=200)
        if "total" in payload:
            base["total"] = int(payload.get("total") or 0)
        if "next_call" in payload and isinstance(payload.get("next_call"), dict):
            base["next_call"] = _sanitize_for_log(payload.get("next_call"))
        if tool == "browser_state_get":
            for key in ("session_id", "profile_id", "session_scope", "visibility", "ready_state", "scope_note"):
                if key in browser_state_payload:
                    base[key] = _truncate_model_text(browser_state_payload.get(key), limit=220)
            if "is_blank_page" in browser_state_payload:
                base["is_blank_page"] = bool(browser_state_payload.get("is_blank_page"))
            if isinstance(browser_state_payload.get("dom_digest"), dict):
                digest = browser_state_payload.get("dom_digest") or {}
                base["dom_digest"] = {
                    "interactive_count": int(digest.get("interactive_count") or 0),
                    "a11y_count": int(digest.get("a11y_count") or 0),
                    "ready_state": _truncate_model_text(digest.get("ready_state"), limit=80),
                }
            interactive_targets = browser_state_payload.get("interactive_targets")
            if isinstance(interactive_targets, list):
                base["interactive_targets"] = [
                    _preview_browser_target(row)
                    for row in interactive_targets[:_MODEL_LIST_PREVIEW_ITEMS]
                    if isinstance(row, dict)
                ]
            a11y_nodes = browser_state_payload.get("a11y_nodes")
            if isinstance(a11y_nodes, list):
                base["a11y_nodes"] = [
                    _preview_browser_target(row)
                    for row in a11y_nodes[:_MODEL_LIST_PREVIEW_ITEMS]
                    if isinstance(row, dict)
                ]
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
    partial_cb: Callable[[dict[str, Any]], None] | None = None,
    partial_interval_ms: int = _TOOL_PARTIAL_INTERVAL_MS,
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
    stop_partial = threading.Event()
    callback_lock = threading.Lock()
    partial_emitted = False
    partial_interval_s = max(0.1, min(0.3, float(partial_interval_ms or _TOOL_PARTIAL_INTERVAL_MS) / 1000.0))

    def _emit_partial(payload: dict[str, Any]) -> None:
        nonlocal partial_emitted
        if partial_cb is None:
            return
        if not isinstance(payload, dict):
            return
        try:
            with callback_lock:
                partial_emitted = True
                partial_cb(payload)
        except Exception:
            pass

    partial_tick = 0
    use_synthetic_partials = not _structured_progress_tool(safe_tool_name)
    if use_synthetic_partials:
        _emit_partial(
            _tool_partial_state(
                safe_tool_name,
                effective_args,
                partial_tick,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        )

    partial_worker: threading.Thread | None = None
    if partial_cb is not None and use_synthetic_partials:
        def _partial_loop() -> None:
            nonlocal partial_tick
            while not stop_partial.wait(partial_interval_s):
                partial_tick += 1
                _emit_partial(
                    _tool_partial_state(
                        safe_tool_name,
                        effective_args,
                        partial_tick,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                    )
                )

        partial_worker = threading.Thread(target=_partial_loop, daemon=True, name="aelin-tool-partial")
        partial_worker.start()
    try:
        if isinstance(synthetic_result, dict):
            result = dict(synthetic_result)
        else:
            result = tool_hub.execute(
                safe_tool_name,
                effective_args,
                progress_cb=_emit_partial if partial_cb is not None else None,
            )
        if not bool(result.get("ok", True)):
            status = "failed"
            error = str(result.get("error") or "tool_not_ok")[:180]
    except Exception as exc:
        status = "failed"
        error = str(exc)[:180]
        result = {"ok": False, "error": error}
    finally:
        if partial_cb is not None and partial_emitted and _progress_sensitive_tool(safe_tool_name):
            min_visible_ms = max(
                0,
                int(getattr(settings, "aelin_agent_loop_progress_min_visible_ms", 320) or 320),
            )
            while int((time.perf_counter() - started) * 1000) < min_visible_ms:
                time.sleep(0.04)
        stop_partial.set()
        if partial_worker is not None:
            partial_worker.join(timeout=0.05)
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
    record_trace: bool = True,
    trace_emit_cb: Callable[[AgentLoopTraceStep], None] | None = None,
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
    if record_trace:
        step = AgentLoopTraceStep(
            stage="agent_loop_tool",
            status=status,
            detail=f"{tool_name}:{error or 'ok'}",
            count=1,
        )
        trace_steps.append(step)
        if trace_emit_cb is not None:
            try:
                trace_emit_cb(step)
            except Exception:
                pass
    return status == "completed"


def flush_pending_reads(
    *,
    pending_reads: list[dict[str, Any]],
    tool_hub: AelinToolHub,
    round_index: int,
    messages: list[dict[str, Any]],
    tool_runs: list[AgentLoopToolRun],
    trace_steps: list[AgentLoopTraceStep],
    tool_event_cb: Callable[[dict[str, Any]], None] | None = None,
    record_tool_trace: bool = True,
    trace_emit_cb: Callable[[AgentLoopTraceStep], None] | None = None,
) -> int:
    if not pending_reads:
        return 0
    batch = list(pending_reads)
    pending_reads.clear()
    start_step = AgentLoopTraceStep(
        stage="agent_loop_read_batch",
        status="running",
        detail=f"parallel_reads={len(batch)}",
        count=len(batch),
    )
    trace_steps.append(start_step)
    if trace_emit_cb is not None:
        try:
            trace_emit_cb(start_step)
        except Exception:
            pass

    results: list[tuple[str, dict[str, Any], str, int] | None] = [None] * len(batch)
    max_workers = max(1, min(4, len(batch)))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="aelin-loop-read") as pool:
        future_map: dict[Any, int] = {}
        for idx, item in enumerate(batch):
            tool_name = str(item.get("tool_name") or "")
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            tc_id = str(item.get("tc_id") or "")
            stage = str(item.get("stage") or "").strip()
            if tool_event_cb is not None:
                try:
                    tool_event_cb(
                        {
                            "phase": "start",
                            "round_index": int(round_index),
                            "tool_name": tool_name,
                            "tc_id": tc_id,
                            "args": args,
                            "stage": stage,
                        }
                    )
                except Exception:
                    pass
            def _emit_partial(partial_state: dict[str, Any], *, _round=int(round_index), _tool=tool_name, _tc=tc_id, _args=args, _stage=stage) -> None:
                if tool_event_cb is None:
                    return
                try:
                    tool_event_cb(
                        {
                            "phase": "partial",
                            "round_index": _round,
                            "tool_name": _tool,
                            "tc_id": _tc,
                            "args": _args,
                            "stage": _stage,
                            **(partial_state if isinstance(partial_state, dict) else {}),
                        }
                    )
                except Exception:
                    pass
            future = pool.submit(
                execute_tool_call,
                tool_hub=tool_hub,
                tool_name=tool_name,
                args=args,
                partial_cb=_emit_partial if tool_event_cb is not None else None,
            )
            future_map[future] = idx
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
        stage = str(item.get("stage") or "").strip()
        status, result, error, latency_ms = (
            results[idx]
            if isinstance(results[idx], tuple)
            else ("failed", {"ok": False, "error": "unknown"}, "unknown", 0)
        )
        if tool_event_cb is not None:
            try:
                tool_event_cb(
                    {
                        "phase": "end",
                        "round_index": int(round_index),
                        "tool_name": tool_name,
                        "tc_id": tc_id,
                        "args": args,
                        "status": status,
                        "result": _compact_tool_result_for_model(tool_name, result if isinstance(result, dict) else {}),
                        "error": error,
                        "latency_ms": int(latency_ms or 0),
                        "stage": stage,
                    }
                )
            except Exception:
                pass
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
            record_trace=record_tool_trace,
            trace_emit_cb=trace_emit_cb,
        ):
            successful_calls += 1

    done_step = AgentLoopTraceStep(
        stage="agent_loop_read_batch",
        status="completed",
        detail=f"parallel_reads={len(batch)}",
        count=len(batch),
    )
    trace_steps.append(done_step)
    if trace_emit_cb is not None:
        try:
            trace_emit_cb(done_step)
        except Exception:
            pass
    return successful_calls
