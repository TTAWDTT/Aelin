from __future__ import annotations

import json
import re
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.models import AgentMemoryNote
from app.services.agent_memory import AgentMemoryService
from app.services.device_center import (
    apply_device_mode as device_apply_mode,
    capture_device_screen as device_capture_screen,
    collect_device_process_items as device_collect_process_items,
    DeviceScreenCaptureError,
    device_capabilities as device_capabilities_info,
)
from app.services.openviking_bridge import TrackingFileMemoryBridge
from app.services.aelin_attachment_service import AelinAttachmentService, get_aelin_attachment_service
from app.services.aelin_utils import normalize_positive_ints
from app.services.pinchtab_client import get_pinchtab_client
from app.services.llm import LLMService
from app.services.web_search import WebSearchResult, WebSearchService

_TOOL_KEYWORDS = (
    "日记",
    "diary",
    "profile",
    "画像",
    "device",
    "进程",
    "性能",
    "模式",
    "memory",
    "context",
    "检索",
    "查一下",
    "搜索",
    "上网",
    "联网",
    "新闻",
    "最新",
    "web",
    "屏幕",
    "截图",
    "screen",
    "screen_get",
    "browser",
    "网页",
    "页面",
    "点击",
    "输入",
    "navigate",
    "click",
    "type",
    "scroll",
    "session",
    "标签页",
    "浏览器进程",
    "附件",
    "attachment",
    "pdf",
    "docx",
    "pptx",
    "xlsx",
)


def _normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def _safe_int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        out = int(value)
    except Exception:
        out = default
    return max(low, min(high, out))


def _result_ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, **fields}


def _result_error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": str(message or "unknown_error")[:180]}


def _result_items(items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return _result_ok(items=items, total=len(items), **extra)


def should_attempt_aelin_tools(query: str) -> bool:
    text = str(query or "").strip().lower()
    if not text:
        return False
    return any(token in text for token in _TOOL_KEYWORDS)


class AelinToolHub:
    def __init__(
        self,
        *,
        db: Session,
        user_id: int,
        workspace: str,
        memory_service: AgentMemoryService,
        file_memory_bridge: TrackingFileMemoryBridge,
        web_search_service: WebSearchService | None = None,
        attachment_service: AelinAttachmentService | None = None,
        available_attachment_ids: list[int] | None = None,
    ) -> None:
        self.db = db
        self.user_id = int(user_id)
        self.workspace = _normalize_workspace(workspace)
        self._memory = memory_service
        self._file_memory = file_memory_bridge
        self._web_search = web_search_service or WebSearchService()
        self._attachments = attachment_service or get_aelin_attachment_service()
        self._available_attachment_ids = normalize_positive_ints(available_attachment_ids, cap=20)

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
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
                    "name": "diary",
                    "description": "检索或读取 Aelin 的日记文件记忆。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["search", "read"]},
                            "query": {"type": "string"},
                            "path": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                        },
                        "required": ["action"],
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
                    "description": "读取设备能力、进程占用，或切换设备模式。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["capabilities", "processes", "mode_apply"]},
                            "sort_by": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                            "mode": {"type": "string"},
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
                            "action": {"type": "string", "enum": ["search", "search_and_fetch"]},
                            "query": {"type": "string"},
                            "max_results": {"type": "integer", "minimum": 1, "maximum": 15},
                            "fetch_top_k": {"type": "integer", "minimum": 0, "maximum": 6},
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
                            "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
                            "mode": {"type": "string", "enum": ["keyword", "hybrid"]},
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
                            "max_edge": {"type": "integer", "minimum": 640, "maximum": 4096},
                            "format": {"type": "string", "enum": ["jpeg", "png"]},
                            "quality": {"type": "integer", "minimum": 35, "maximum": 95},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "pinchtab",
                    "description": (
                        "通过本地 PinchTab 服务在真实浏览器中打开网页、查看内容并点击元素。"
                        "用于所有需要“上网”“浏览网页”“操作 X/Twitter 等网站”的任务，这是你唯一的网页浏览方式。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["health", "launch_instance", "open_tab", "snapshot", "text", "click"],
                            },
                            "instance_id": {"type": "string"},
                            "tab_id": {"type": "string"},
                            "url": {"type": "string"},
                            "ref": {"type": "string"},
                        },
                        "required": ["action"],
                    },
                },
            },
        ]

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = str(name or "").strip().lower()
        if tool == "context_get":
            return self._tool_context_get(args)
        if tool == "diary":
            return self._tool_diary(args)
        if tool == "profile":
            return self._tool_profile(args)
        if tool == "device":
            return self._tool_device(args)
        if tool == "web_search":
            return self._tool_web_search(args)
        if tool == "attachment_search":
            return self._tool_attachment_search(args)
        if tool == "screen_get":
            return self._tool_screen_get(args)
        if tool == "pinchtab":
            return self._tool_pinchtab(args)
        return _result_error(f"unsupported tool: {tool}")

    def _tool_context_get(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()[:400]
        limit = _safe_int(args.get("max_items"), 8, low=1, high=20)
        snapshot = self._memory.snapshot(self.db, self.user_id, query=query)
        focus_items = list(snapshot.get("focus_items") or [])[:limit]
        todos = self._memory.list_todos(self.db, self.user_id, include_done=False, limit=limit)
        return _result_ok(
            workspace=self.workspace,
            summary=str(snapshot.get("summary") or ""),
            focus_items=focus_items,
            todos=todos,
        )

    def _tool_diary(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "search").strip().lower()
        if action == "read":
            path = str(args.get("path") or "").strip()
            if not path:
                return _result_error("missing path")
            row = self._file_memory.read_memory_markdown(
                user_id=self.user_id,
                workspace=self.workspace,
                path=path,
            )
            if not row:
                return _result_error("not found")
            return _result_ok(
                title=str(row.get("title") or ""),
                path=str(row.get("path") or ""),
                content=str(row.get("content") or "")[:4000],
                entry_kind=str(row.get("entry_kind") or ""),
            )

        query = str(args.get("query") or "").strip()[:240]
        limit = _safe_int(args.get("limit"), 8, low=1, high=20)
        hits = self._file_memory.search(
            user_id=self.user_id,
            workspace=self.workspace,
            query=query,
            limit=limit,
            include_diary=True,
        )
        items = [
            {
                "title": str(it.title),
                "path": str(it.path),
                "preview": str(it.preview)[:220],
                "score": float(it.score),
                "entry_kind": str(it.entry_kind),
                "topic_path": str(it.topic_path),
            }
            for it in hits[:limit]
        ]
        return _result_items(items)

    def _tool_profile(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "get").strip().lower()
        if action == "append_note":
            note = re.sub(r"\s+", " ", str(args.get("note") or "")).strip()[:500]
            if not note:
                return _result_error("empty note")
            row = self._memory.add_note(
                self.db,
                self.user_id,
                note,
                kind="profile",
                source=f"profile:{self.workspace}",
            )
            return _result_ok(note_id=int(getattr(row, "id", 0) or 0), note=note)

        max_items = _safe_int(args.get("max_items"), 12, low=1, high=24)
        notes = list(
            self.db.scalars(
                select(AgentMemoryNote)
                .where(
                    AgentMemoryNote.user_id == self.user_id,
                    AgentMemoryNote.kind.in_(["profile", "identity", "preference", "user_profile", "user_note", "manual_note"]),
                )
                .order_by(AgentMemoryNote.updated_at.desc(), AgentMemoryNote.id.desc())
                .limit(max_items)
            )
        )
        items = [
            {
                "id": int(it.id),
                "kind": str(it.kind or ""),
                "content": str(it.content or "")[:220],
                "source": str(it.source or ""),
                "updated_at": it.updated_at.isoformat() if getattr(it, "updated_at", None) else "",
            }
            for it in notes
        ]
        return _result_items(items)

    def _tool_device(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "capabilities").strip().lower()
        if action == "processes":
            sort_by = str(args.get("sort_by") or "cpu").strip().lower() or "cpu"
            limit = _safe_int(args.get("limit"), 8, low=1, high=20)
            rows = device_collect_process_items(sort_by=sort_by, limit=limit)
            items = [
                {
                    "pid": int(it.pid),
                    "name": str(it.name),
                    "cpu_percent": float(it.cpu_percent or 0.0),
                    "memory_mb": float(it.memory_mb or 0.0),
                    "anomaly_score": float(it.anomaly_score or 0.0),
                }
                for it in rows
            ]
            return _result_items(items)
        if action == "mode_apply":
            mode = str(args.get("mode") or "").strip().lower()
            if not mode:
                return _result_error("missing mode")
            result = device_apply_mode(mode=mode)
            return _result_ok(
                mode=str(result.get("mode") or mode),
                status=str(result.get("status") or ""),
                summary=str(result.get("summary") or ""),
                warnings=list(result.get("warnings") or []),
            )
        return _result_ok(**device_capabilities_info())

    def _tool_web_search(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "search_and_fetch").strip().lower()
        if action not in {"search", "search_and_fetch"}:
            return _result_error("unsupported action")
        query = str(args.get("query") or "").strip()[:400]
        if not query:
            return _result_error("missing query")

        max_results = _safe_int(args.get("max_results"), 15, low=1, high=15)
        fetch_top_k = _safe_int(args.get("fetch_top_k"), 3, low=0, high=6)
        fetch_top_k = min(fetch_top_k, max_results)

        rows: list[WebSearchResult] = []
        if action == "search":
            rows = list(self._web_search.search(query, max_results=max_results) or [])
        else:
            rows = list(
                self._web_search.search_and_fetch(
                    query,
                    max_results=max_results,
                    fetch_top_k=fetch_top_k,
                )
                or []
            )

        providers: set[str] = set()
        items: list[dict[str, Any]] = []
        for idx, row in enumerate(rows[:max_results], start=1):
            title = str(getattr(row, "title", "") or "").strip()
            url = str(getattr(row, "url", "") or "").strip()
            snippet = str(getattr(row, "snippet", "") or "").strip()
            provider = str(getattr(row, "provider", "") or "").strip() or "unknown"
            source = str(getattr(row, "source", "") or "").strip() or "web"
            fetched_excerpt = str(getattr(row, "fetched_excerpt", "") or "").strip()
            fetch_mode = str(getattr(row, "fetch_mode", "") or "").strip() or "none"
            rank = _safe_int(getattr(row, "rank", idx), idx, low=1, high=9999)
            providers.add(provider)
            items.append(
                {
                    "title": title[:220],
                    "url": url[:600],
                    "snippet": snippet[:320],
                    "provider": provider[:32],
                    "source": source[:24],
                    "fetch_mode": fetch_mode[:24],
                    "rank": rank,
                    "fetched_excerpt": fetched_excerpt[:1200],
                }
            )

        return _result_items(
            items,
            query=query,
            action=action,
            providers=sorted(providers),
            fetch_top_k=(fetch_top_k if action == "search_and_fetch" else 0),
        )

    def _tool_attachment_search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()[:500]
        if not query:
            return _result_error("missing query")
        raw_ids = args.get("attachment_ids")
        attachment_ids: list[int] = normalize_positive_ints(raw_ids if isinstance(raw_ids, list) else [], cap=20)
        if not attachment_ids:
            attachment_ids = list(self._available_attachment_ids)
        if not attachment_ids:
            return _result_error("missing attachment_ids")
        top_k = _safe_int(args.get("top_k"), 5, low=1, high=20)
        mode = str(args.get("mode") or "keyword").strip().lower()
        if mode not in {"keyword", "hybrid"}:
            mode = "keyword"
        result = self._attachments.search(
            self.db,
            user_id=self.user_id,
            workspace=self.workspace,
            query=query,
            attachment_ids=attachment_ids,
            top_k=top_k,
            mode=mode,
        )
        if not bool(result.get("ok")):
            return _result_error(str(result.get("error") or "attachment_search_failed"))
        return _result_ok(
            query=query,
            mode=mode,
            attachment_ids=list(result.get("attachment_ids") or []),
            total=int(result.get("total") or 0),
            content=str(result.get("content") or "")[:8000],
            hits=list(result.get("hits") or []),
        )

    def _tool_screen_get(self, args: dict[str, Any]) -> dict[str, Any]:
        display_id = str(args.get("display_id") or "").strip()[:64]
        max_edge = _safe_int(args.get("max_edge"), 1280, low=640, high=4096)
        fmt = "png" if str(args.get("format") or "").strip().lower() == "png" else "jpeg"
        quality = _safe_int(args.get("quality"), 72, low=35, high=95)
        try:
            shot = device_capture_screen(
                display_id=display_id,
                max_edge=max_edge,
                image_format=fmt,
                quality=quality,
            )
        except DeviceScreenCaptureError as exc:
            return _result_error(f"screen_get_failed:{exc.detail}")
        except Exception as exc:
            return _result_error(f"screen_get_failed:{str(exc)[:160]}")

        return _result_ok(
            data_url=str(shot.get("data_url") or ""),
            name=str(shot.get("name") or "")[:120],
            width=max(0, int(shot.get("width") or 0)),
            height=max(0, int(shot.get("height") or 0)),
            source_display=str(shot.get("source_display") or "")[:64],
            captured_at=str(shot.get("captured_at") or "")[:64],
        )

    def _tool_pinchtab(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "").strip().lower()
        client = get_pinchtab_client()
        if not action:
            return _result_error("missing action")
        if action == "health":
            out = client.health()
            return out if isinstance(out, dict) else _result_error("pinchtab_health_failed")
        if action == "launch_instance":
            return client.launch_instance()
        if action == "open_tab":
            instance_id = str(args.get("instance_id") or "").strip()
            url = str(args.get("url") or "").strip()
            if not instance_id or not url:
                return _result_error("missing instance_id or url")
            return client.open_tab(instance_id=instance_id, url=url)
        if action == "snapshot":
            tab_id = str(args.get("tab_id") or "").strip()
            if not tab_id:
                return _result_error("missing tab_id")
            return client.snapshot(tab_id=tab_id)
        if action == "text":
            tab_id = str(args.get("tab_id") or "").strip()
            if not tab_id:
                return _result_error("missing tab_id")
            return client.text(tab_id=tab_id)
        if action == "click":
            tab_id = str(args.get("tab_id") or "").strip()
            ref = str(args.get("ref") or "").strip()
            if not tab_id or not ref:
                return _result_error("missing tab_id or ref")
            return client.action(tab_id=tab_id, kind="click", ref=ref)
        return _result_error(f"unsupported pinchtab action: {action}")


def _safe_load_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _execute_tool_call(tool_hub: AelinToolHub, *, name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any], str, int]:
    status = "completed"
    result: dict[str, Any] = {}
    error = ""
    started = time.perf_counter()
    try:
        result = tool_hub.execute(name, args)
        if not bool(result.get("ok", True)):
            status = "failed"
            error = str(result.get("error") or "tool returned not ok")[:180]
    except Exception as exc:
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
    if provider == "rule_based":
        return [], "provider_rule_based"
    client = getattr(service, "client", None)
    if client is None:
        return [], "llm_not_configured"

    tools = tool_hub.tool_definitions()
    if not tools:
        return [], "tool_definitions_empty"

    messages = [
        {
            "role": "system",
            "content": (
                "You are a tool planner for Aelin. "
                "Only call tools when the user query clearly needs memory/profile/diary/tracking/device/screen/browser/attachment operations. "
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
    except Exception as exc:
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
        status, result, error, latency_ms = _execute_tool_call(tool_hub, name=name, args=args)
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


def summarize_tool_results_for_prompt(runs: list[dict[str, Any]], *, max_lines: int = 8) -> list[str]:
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
            note = f"total={result.get('total')}, providers={','.join(list(result.get('providers') or [])[:3])}"
        elif name == "attachment_search":
            note = f"total={result.get('total')}, attachments={','.join([str(x) for x in list(result.get('attachment_ids') or [])[:6]])}"
        elif name in {"diary", "profile", "context_get", "device", "screen_get"}:
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
