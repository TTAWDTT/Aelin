from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.services.agent_memory import AgentMemoryService, serialize_focus_item
from app.services.aelin_attachment_service import (
    AelinAttachmentService,
    get_aelin_attachment_service,
)
from app.services.aelin_utils import normalize_positive_ints
from app.services.device_center import (
    activate_desktop_module,
    capture_device_screen as device_capture_screen,
    DesktopPluginActionError,
    DeviceScreenCaptureError,
    device_status_snapshot,
    open_desktop_external_url,
)
from app.services.google_workspace_cli import get_google_workspace_cli_service
from app.services.llm import LLMService
from app.services.web_search import WebSearchService
from app.services.tools_device import tool_device, tool_screen_get
from app.services.tools_files import tool_attachment_search
from app.services.tools_gws import tool_google_workspace
from app.services.tools_web import tool_web_search
from app.services.tools_context import tool_context_get, tool_profile


def _normalize_workspace(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def _safe_int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        out = int(value)
    except Exception:  # noqa: BLE001
        out = default
    return max(low, min(high, out))


def _result_ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, **fields}


def _result_error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": str(message or "unknown_error")[:180]}


def _result_items(items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return _result_ok(items=items, total=len(items), **extra)


def _is_http_url(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _safe_load_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:  # noqa: BLE001
        return {}
    return parsed if isinstance(parsed, dict) else {}


class AelinToolHub:
    """
    Thin registry that binds the current DB/user/workspace context to a small
    set of capability tools (memory/profile/device/web/attachments/GWS).

    DeepAgents 只依赖这里暴露的工具集合，其余复杂逻辑（旧浏览器 runtime、
    旧式 skill 注入等）已经完全移除。
    """

    def __init__(
        self,
        *,
        db: Session,
        user_id: int,
        workspace: str,
        memory_service: AgentMemoryService,
        web_search_service: WebSearchService | None = None,
        attachment_service: AelinAttachmentService | None = None,
        available_attachment_ids: list[int] | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        self.db = db
        self.user_id = int(user_id)
        self.workspace = _normalize_workspace(workspace)
        self._memory = memory_service
        self._web_search = web_search_service or WebSearchService()
        self._attachments = attachment_service or get_aelin_attachment_service()
        self._available_attachment_ids = normalize_positive_ints(
            available_attachment_ids, cap=20
        )
        # Optional reference to the current LLM service so tools can delegate
        # sub-tasks in the future if needed.
        self._llm_service = llm_service
        self._tool_definitions_cache: list[dict[str, Any]] | None = None

    def tool_definitions(self) -> list[dict[str, Any]]:
        """
        Return OpenAI-style tool definitions for planner/debug/front-end use.

        DeepAgents 本身只使用 web_search/attachment_search/google_workspace/
        device/screen_get 这几个能力工具，但为了 UI 展示和结构化 planner，
        这里同时暴露 context_get/profile。
        """
        if self._tool_definitions_cache is not None:
            return self._tool_definitions_cache

        self._tool_definitions_cache = [
            {
                "type": "function",
                "function": {
                    "name": "context_get",
                    "description": "读取当前用户的上下文记忆摘要、重点消息与待办概览。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_items": {"type": "integer", "minimum": 1, "maximum": 20},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "profile",
                    "description": "读取或追加用户画像/备注。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["get", "append_note"]},
                            "note": {"type": "string"},
                            "max_items": {"type": "integer", "minimum": 1, "maximum": 24},
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "device",
                    "description": (
                        "统一的设备工具。"
                        "使用 action=status 查询设备状态，action=open_url 打开网页，"
                        "action=open_aelin 唤起 Aelin 桌面页。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["status", "open_url", "open_aelin"],
                            },
                            "url": {"type": "string"},
                            "route": {"type": "string"},
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "执行联网搜索，返回标题、链接、摘要，并可抓取正文片段。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["search", "search_and_fetch"],
                            },
                            "query": {"type": "string"},
                            "max_results": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 15,
                            },
                            "fetch_top_k": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 6,
                            },
                        },
                        "required": ["action", "query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "attachment_search",
                    "description": "在已上传附件中检索与问题最相关的片段，并返回可引用来源信息。若不传 attachment_ids，将默认使用 available_attachment_ids。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "attachment_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "maxItems": 20,
                                "description": "可选。默认使用 available_attachment_ids。",
                            },
                            "top_k": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 20,
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["keyword", "hybrid"],
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "screen_get",
                    "description": "抓取当前屏幕截图，供后续步骤进行视觉分析。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "display_id": {"type": "string"},
                            "max_edge": {
                                "type": "integer",
                                "minimum": 640,
                                "maximum": 4096,
                            },
                            "format": {"type": "string", "enum": ["jpeg", "png"]},
                            "quality": {
                                "type": "integer",
                                "minimum": 35,
                                "maximum": 95,
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "google_workspace",
                    "description": "使用本地 gws CLI 访问 Google Workspace（Gmail / Drive / Calendar / Docs 等）的信息，并在用户明确同意时执行少量写操作（发邮件、创建日历事件、创建文档等）。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "calendar_id": {"type": "string"},
                            "time_min": {"type": "string"},
                            "time_max": {"type": "string"},
                            "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                            "single_events": {"type": "boolean"},
                            "event_summary": {"type": "string"},
                            "event_description": {"type": "string"},
                            "event_start": {"type": "string"},
                            "event_end": {"type": "string"},
                            "event_attendees": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 16,
                            },
                            "query": {"type": "string"},
                            "include_spam_trash": {"type": "boolean"},
                            "message_id": {"type": "string"},
                            "format": {"type": "string"},
                            "email_to": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 16,
                            },
                            "email_cc": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 16,
                            },
                            "email_bcc": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 16,
                            },
                            "email_subject": {"type": "string"},
                            "email_body": {"type": "string"},
                            "docs_title": {"type": "string"},
                            "docs_content": {"type": "string"},
                        },
                        "required": ["action"],
                    },
                },
            },
        ]
        return self._tool_definitions_cache

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = str(name or "").strip().lower()
        if tool == "context_get":
            return tool_context_get(self, args)
        if tool == "profile":
            return tool_profile(self, args)
        if tool == "device":
            return tool_device(self, args)
        if tool == "web_search":
            return tool_web_search(self, args)
        if tool == "attachment_search":
            return tool_attachment_search(self, args)
        if tool == "screen_get":
            return tool_screen_get(self, args)
        if tool == "google_workspace":
            return tool_google_workspace(self, args)
        return _result_error(f"unsupported tool: {tool}")

    # ---- device helpers (used by tools_device) -----------------------------------

    def _tool_device_status(self, args: dict[str, Any]) -> dict[str, Any]:
        _ = args
        snapshot = device_status_snapshot()
        return _result_ok(
            platform=str(snapshot.get("platform") or "unknown"),
            capabilities=dict(snapshot.get("capabilities") or {}),
            notes=list(snapshot.get("notes") or []),
            desktop_plugin_reachable=bool(snapshot.get("desktop_plugin_reachable")),
            desktop_plugin_configured=bool(snapshot.get("desktop_plugin_configured")),
            summary=(
                f"platform={str(snapshot.get('platform') or 'unknown')}; "
                f"plugin_reachable={1 if bool(snapshot.get('desktop_plugin_reachable')) else 0}"
            ),
        )

    def _tool_desktop_open_url(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args.get("url") or "").strip()
        if not url:
            return _result_error("missing url")
        if not _is_http_url(url):
            return _result_error("invalid_url_scheme")
        try:
            result = open_desktop_external_url(url)
        except DesktopPluginActionError as exc:
            return _result_error(f"desktop_open_url_failed:{exc.detail}")
        except Exception as exc:  # noqa: BLE001
            return _result_error(f"desktop_open_url_failed:{str(exc)[:160]}")
        return _result_ok(
            url=str(result.get("url") or url),
            opened=bool(result.get("opened")),
            detail=str(result.get("detail") or ""),
            summary=f"已尝试打开链接: {str(result.get('url') or url)[:220]}",
        )

    def _tool_desktop_open_aelin(self, args: dict[str, Any]) -> dict[str, Any]:
        route = str(args.get("route") or "/").strip() or "/"
        try:
            result = activate_desktop_module(route)
        except DesktopPluginActionError as exc:
            return _result_error(f"desktop_open_aelin_failed:{exc.detail}")
        except Exception as exc:  # noqa: BLE001
            return _result_error(f"desktop_open_aelin_failed:{str(exc)[:160]}")
        return _result_ok(
            route=str(result.get("route") or route),
            url=str(result.get("url") or ""),
            opened=bool(result.get("opened", result.get("activated"))),
            detail=str(result.get("detail") or ""),
            summary=f"Aelin 已切换到 {str(result.get('route') or route)[:120]}",
        )


def _execute_tool_call(
    tool_hub: AelinToolHub, *, name: str, args: dict[str, Any]
) -> tuple[str, dict[str, Any], str, int]:
    status = "completed"
    result: dict[str, Any] = {}
    error = ""
    started = time.perf_counter()
    try:
        result = tool_hub.execute(name, args)
        if not bool(result.get("ok", True)):
            status = "failed"
            error = str(result.get("error") or "tool returned not ok")[:180]
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = str(exc)[:180]
        result = _result_error(error)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return status, result, error, latency_ms


def run_aelin_structured_tools(
    *,
    service: LLMService,
    provider: str,
    query: str,
    memory_summary: str,
    tool_hub: AelinToolHub,
    max_calls: int = 2,
) -> tuple[list[dict[str, Any]], str]:
    """
    Lightweight planner that lets a model propose a small number of tool calls.

    该函数主要用于调试和 UI 上的“工具跟踪”，不会参与 DeepAgents 主回路。
    """
    if provider == "rule_based":
        return [], "provider_rule_based"
    client = getattr(service, "client", None)
    if client is None:
        return [], "llm_not_configured"

    tools = list(tool_hub.tool_definitions())
    if not tools:
        return [], "tool_definitions_empty"

    messages = [
        {
            "role": "system",
            "content": (
                "You are a tool planner for Aelin. "
                "Only call tools when the user query clearly needs memory/profile/device/"
                "screen/browser/attachment operations. "
                "At most call 2 tools. If no tool is needed, respond directly without tool calls."
            ),
        },
        {
            "role": "user",
            "content": f"query={query[:500]}\nmemory_summary={memory_summary[:600]}",
        },
    ]
    try:
        response = client.chat.completions.create(
            model=service.config.model,
            messages=messages,
            temperature=0.0,
            max_tokens=180,
            tools=tools,
            tool_choice="auto",
        )
    except Exception as exc:  # noqa: BLE001
        return [], f"planner_error:{str(exc)[:120]}"

    choice = response.choices[0] if response and response.choices else None
    message = getattr(choice, "message", None) if choice else None
    raw_calls = list(getattr(message, "tool_calls", []) or [])
    if not raw_calls:
        return [], "no_tool_call"

    out: list[dict[str, Any]] = []
    cap = max(1, min(4, int(max_calls or 2)))
    for tc in raw_calls[:cap]:
        fn = getattr(tc, "function", None)
        name = str(getattr(fn, "name", "") or "").strip()
        args = _safe_load_json(str(getattr(fn, "arguments", "{}") or "{}"))
        status, result, error, latency_ms = _execute_tool_call(
            tool_hub, name=name, args=args
        )
        out.append(
            {
                "name": name,
                "args": args,
                "status": status,
                "latency_ms": latency_ms,
                "result": result,
                "error": error,
            }
        )
    return out, ""


def summarize_tool_results_for_prompt(
    runs: list[dict[str, Any]], *, max_lines: int = 8
) -> list[str]:
    """
    Build a compact textual summary of recent tool runs for debugging/prompts.
    """
    lines: list[str] = []
    for run in runs[: max(1, int(max_lines))]:
        name = str(run.get("name") or "tool").strip()
        status = str(run.get("status") or "completed").strip().lower()
        result = run.get("result") if isinstance(run.get("result"), dict) else {}
        error = str(run.get("error") or "").strip()

        note = ""
        if status != "completed":
            note = error or "failed"
        elif name == "web_search":
            note = (
                f"total={result.get('total')}, "
                f"providers={','.join(list(result.get('providers') or [])[:3])}"
            )
        elif name == "attachment_search":
            note = (
                f"total={result.get('total')}, attachments="
                f"{','.join([str(x) for x in list(result.get('attachment_ids') or [])[:6]])}"
            )
        elif name in {"profile", "context_get", "device", "screen_get"}:
            if "total" in result:
                note = f"total={result.get('total')}"
            elif "summary" in result:
                note = str(result.get("summary") or "")[:120]
            else:
                note = json.dumps(result, ensure_ascii=False)[:140]
        else:
            note = json.dumps(result, ensure_ascii=False)[:140]

        lines.append(f"- [{name}/{status}] {note}".strip())
    return lines


__all__ = [
    "AelinToolHub",
    "_safe_int",
    "_result_ok",
    "_result_error",
    "_result_items",
    "DeviceScreenCaptureError",
    "device_capture_screen",
    "get_google_workspace_cli_service",
    "run_aelin_structured_tools",
    "summarize_tool_results_for_prompt",
]
