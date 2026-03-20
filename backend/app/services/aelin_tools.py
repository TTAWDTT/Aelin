from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher
import inspect
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.models import AgentMemoryNote
from app.services.agent_memory import AgentMemoryService, serialize_focus_item
from app.services.device_center import (
    activate_desktop_module,
    capture_device_screen as device_capture_screen,
    DesktopPluginActionError,
    DeviceScreenCaptureError,
    device_status_snapshot,
    open_desktop_external_url,
)
from app.services.aelin_attachment_service import AelinAttachmentService, get_aelin_attachment_service
from app.services.aelin_planes import close_plane_task, get_active_plane_task, plane_catalog_entries
from app.services.aelin_utils import normalize_positive_ints
from app.services.google_workspace_cli import get_google_workspace_cli_service
from app.services.pinchtab_launcher import ensure_pinchtab_started
from app.services.pinchtab_client import get_pinchtab_client
from app.services.plane_runtime import get_plane_registry_entry
from app.services.llm import LLMService
from app.services.web_search import WebSearchResult, WebSearchService
from app.services.tools_web import tool_web_search
from app.services.tools_gws import tool_google_workspace
from app.services.tools_skill import tool_skill
from app.services.tools_files import tool_attachment_search
from app.services.tools_device import tool_device, tool_screen_get
from app.services.tools_browser_plane import (
    tool_plane,
    tool_pinchtab,
    tool_pinchtab_agent,
    tool_pinchtab_session,
)

_TOOL_KEYWORDS = (
    "profile",
    "画像",
    "device",
    "进程",
    "性能",
    "模式",
    "status",
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
    "screenshot",
    "open url",
    "打开网址",
    "打开链接",
    "打开aelin",
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
_PLANE_CONTINUATION_HINTS = (
    "continue",
    "resume",
    "pick up",
    "pick-up",
    "follow up",
    "same task",
    "same browser task",
    "keep going",
    "继续",
    "接着",
    "恢复",
    "继续处理",
    "继续这个任务",
    "接着做",
    "刚才",
    "上一个",
    "之前那个",
    "同一个任务",
)
_GOAL_COMMON_TOKENS = {
    "open",
    "read",
    "check",
    "view",
    "look",
    "browse",
    "page",
    "website",
    "site",
    "task",
    "summary",
    "summarize",
    "continue",
    "resume",
    "login",
    "log",
    "in",
    "and",
    "the",
    "a",
    "an",
    "to",
    "for",
    "with",
    "on",
    "my",
    "your",
    "help",
}
_GOAL_COMMON_CJK_PHRASES = (
    "帮我看看",
    "帮我查看",
    "帮我处理",
    "继续处理",
    "关注列表",
    "继续这个任务",
    "同一个任务",
    "我已经",
    "已完成",
    "完成了",
    "帮我",
    "查看",
    "看看",
    "看下",
    "打开",
    "读取",
    "阅读",
    "继续",
    "接着",
    "恢复",
    "处理",
    "总结",
    "概括",
    "分析",
    "已经",
    "好了",
    "完成",
    "订单",
    "列表",
    "关注",
    "页面",
    "网站",
    "网页",
    "链接",
    "网址",
    "详情",
    "任务",
    "内容",
    "文本",
    "教程",
    "文档",
    "邮件",
    "附件",
    "一下",
    "我的",
    "这个",
    "那个",
    "当前",
    "继续",
    "接着",
    "恢复",
    "登录后",
    "然后",
    "并且",
    "并",
    "看",
)
_STALE_PLANE_ERRORS = {"unknown_session_id", "plane_missing_session_id", "unknown_task_id"}
_CHECKPOINT_RESPONSE_HINTS = (
    "我已经",
    "已经",
    "好了",
    "完成了",
    "完成",
    "继续",
    "恢复",
    "resume",
    "done",
    "ok",
    "logged in",
    "login",
    "验证码",
    "验证",
    "2fa",
    "code",
)
_CHECKPOINT_GENERIC_ANCHORS = {"登录", "验证", "验证码", "2fa", "code", "login", "logged", "done", "ok"}


def _build_plane_adapter_for_entry(entry, *, tool_hub: "AelinToolHub"):
    """
    Construct a PlaneAdapter instance from a registry entry.

    The adapter factory for each plane receives a shared context subset
    (db/user_id/workspace). Plane-specific runtime hooks (such as the
    PinchTab session executor) are injected only when the factory declares
    the corresponding parameter, so that non-browser planes are not coupled
    to browser-specific arguments.
    """
    kwargs: dict[str, Any] = {
        "db": getattr(tool_hub, "db", None),
        "user_id": int(getattr(tool_hub, "user_id", 0) or 0),
        "workspace": str(getattr(tool_hub, "workspace", "default") or "default"),
    }

    try:
        sig = inspect.signature(entry.adapter_factory)
        params = sig.parameters
    except Exception:
        params = {}

    if "session_executor" in params:
        kwargs["session_executor"] = lambda *, action, session_id="", goal="": _execute_pinchtab_session_action(
            tool_hub,
            action=action,
            session_id=session_id,
            goal=goal,
        )

    return entry.adapter_factory(**kwargs)


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


def _is_http_url(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _normalize_goal_text(raw: str) -> str:
    return re.sub(r"\s+", " ", str(raw or "").strip().lower())[:800]


def _extract_goal_tokens(raw: str) -> set[str]:
    text = _normalize_goal_text(raw)
    if not text:
        return set()
    tokens = {
        token
        for token in re.findall(r"\b[a-z][a-z0-9_-]{1,31}\b", text)
        if token not in _GOAL_COMMON_TOKENS
    }
    if re.search(r"(^|[^a-z0-9])x([^a-z0-9]|$)", text):
        tokens.add("x")
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,20}", text):
        cleaned = str(chunk)
        for phrase in _GOAL_COMMON_CJK_PHRASES:
            cleaned = cleaned.replace(phrase, " ")
        for part in cleaned.split():
            normalized = part.strip()
            if 2 <= len(normalized) <= 8:
                tokens.add(normalized)
    return tokens


def _extract_host_tokens_from_value(raw: str) -> set[str]:
    tokens: set[str] = set()
    text = _normalize_goal_text(raw)
    if not text:
        return tokens
    candidates = re.findall(r"https?://[^\s]+", text)
    if not candidates:
        candidates = re.findall(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", text)
    for candidate in candidates[:8]:
        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        host = str(parsed.netloc or parsed.path or "").strip().lower()
        if not host:
            continue
        if host.startswith("www."):
            host = host[4:]
        parts = [part for part in host.split(".") if part]
        for part in parts:
            if part in {"com", "cn", "net", "org", "io", "co", "app"}:
                continue
            tokens.add(part)
    return tokens


def _goal_has_continuation_hint(goal: str) -> bool:
    text = _normalize_goal_text(goal)
    if not text:
        return False
    return any(hint in text for hint in _PLANE_CONTINUATION_HINTS)


def _goals_look_related(*, active_task: dict[str, Any], new_goal: str) -> bool:
    old_goal = _normalize_goal_text(str(active_task.get("goal") or ""))
    new_goal_normalized = _normalize_goal_text(new_goal)
    if not old_goal or not new_goal_normalized:
        return False
    old_goal_tokens = _extract_goal_tokens(old_goal)
    new_goal_tokens = _extract_goal_tokens(new_goal_normalized)
    shared_tokens = old_goal_tokens & new_goal_tokens
    host_tokens = _extract_host_tokens_from_value(str(active_task.get("last_url") or "")) | _extract_host_tokens_from_value(old_goal)
    new_host_tokens = _extract_host_tokens_from_value(new_goal_normalized)
    shared_host = host_tokens and any(token in new_goal_normalized for token in host_tokens)

    if _goal_has_continuation_hint(new_goal_normalized):
        old_anchors = old_goal_tokens | host_tokens
        new_anchors = new_goal_tokens | new_host_tokens
        if old_anchors and new_anchors and not (old_anchors & new_anchors):
            return False
        if shared_host or len(shared_tokens) >= 1 or not new_anchors:
            return True

    shorter_len = min(len(old_goal), len(new_goal_normalized))
    if shorter_len >= 8 and (old_goal in new_goal_normalized or new_goal_normalized in old_goal):
        return True

    similarity = SequenceMatcher(a=old_goal, b=new_goal_normalized).ratio()
    if similarity >= 0.82:
        return True

    if len(shared_tokens) >= 2:
        return True

    if shared_host and similarity >= 0.6:
        return True
    return False


def _should_reuse_active_plane_task(active_task: dict[str, Any] | None, *, goal: str) -> bool:
    if not isinstance(active_task, dict):
        return False
    task_id = " ".join(str(active_task.get("task_id") or "").strip().split())[:96]
    state = str(active_task.get("state") or "").strip().lower()
    if not task_id:
        return False
    if state not in {"queued", "running", "waiting_user", "blocked"}:
        return False
    return _goals_look_related(active_task=active_task, new_goal=goal)


def _query_looks_like_checkpoint_response(query: str) -> bool:
    text = _normalize_goal_text(query)
    if not text:
        return False
    return any(hint in text for hint in _CHECKPOINT_RESPONSE_HINTS)


def should_resume_active_plane_for_query(active_task: dict[str, Any] | None, query: str) -> bool:
    if not isinstance(active_task, dict):
        return False
    normalized_query = _normalize_goal_text(query)
    if not normalized_query:
        return False
    if _goals_look_related(active_task=active_task, new_goal=normalized_query):
        return True
    if str(active_task.get("state") or "").strip().lower() != "waiting_user":
        return False
    if not _query_looks_like_checkpoint_response(normalized_query):
        return False
    prompt = _normalize_goal_text(str(active_task.get("user_prompt") or ""))
    goal = _normalize_goal_text(str(active_task.get("goal") or ""))
    loginish = any(token in f"{prompt}\n{goal}" for token in ("login", "登录", "验证码", "2fa", "验证"))
    if not loginish:
        return False
    old_anchors = _extract_goal_tokens(goal) | _extract_host_tokens_from_value(str(active_task.get("last_url") or ""))
    query_anchors = _extract_goal_tokens(normalized_query) | _extract_host_tokens_from_value(normalized_query)
    extra_query_anchors = {token for token in query_anchors if token not in _CHECKPOINT_GENERIC_ANCHORS}
    if not extra_query_anchors:
        return True
    return bool(old_anchors & extra_query_anchors)


def _should_restart_plane_task_after_reuse_failure(result: dict[str, Any]) -> bool:
    error = str((result or {}).get("error") or "").strip().lower()
    return error in _STALE_PLANE_ERRORS


def should_attempt_aelin_tools(query: str) -> bool:
    text = str(query or "").strip().lower()
    if not text:
        return False
    return any(token in text for token in _TOOL_KEYWORDS)


def _ensure_pinchtab_runtime() -> dict[str, Any] | None:
    try:
        status = ensure_pinchtab_started()
    except Exception as exc:
        return _result_error(f"pinchtab_runtime_failed:{str(exc)[:160]}")
    if bool(status.get("ok")):
        return None
    error = str(status.get("error") or "pinchtab_runtime_unavailable")[:160]
    return _result_error(error)


class AelinToolHub:
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
        self._available_attachment_ids = normalize_positive_ints(available_attachment_ids, cap=20)
        # Optional reference to the current LLM service so tools can delegate
        # sub-tasks (for example, a higher-level pinchtab agent).
        self._llm_service = llm_service
        self._tool_definitions_cache: list[dict[str, Any]] | None = None

    def tool_definitions(self) -> list[dict[str, Any]]:
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
                    "name": "memory",
                    "description": "通过编辑 `/memory/AGENTS.md` 更新长期记忆与待办事项。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["append_fact", "append_preference", "add_todo"],
                            },
                            "content": {
                                "type": "string",
                                "description": "当 action 为 append_fact/append_preference 时，要追加的记忆内容。",
                            },
                            "title": {
                                "type": "string",
                                "description": "当 action=add_todo 时，待办标题。",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "normal", "high"],
                                "description": "当 action=add_todo 时，可选的待办优先级。默认 normal。",
                            },
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
                    "name": "google_workspace",
                    "description": "使用本地 gws CLI 访问 Google Workspace（Gmail / Drive / Calendar / Docs 等）的信息，并在用户明确同意时执行少量写操作（发邮件、创建日历事件、创建文档等）。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": (
                                    "要执行的操作。读能力包括 runtime/auth_status/gmail_list/gmail_get/drive_list/calendar_list，"
                                    "写能力包括 calendar_create_event/gmail_send/gmail_draft/docs_create。"
                                ),
                            },
                            "query": {"type": "string", "description": "Gmail/Drive 检索关键字。"},
                            "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                            "include_spam_trash": {"type": "boolean"},
                            "message_id": {"type": "string", "description": "要读取的 Gmail 消息 ID。"},
                            "format": {
                                "type": "string",
                                "enum": ["full", "metadata", "minimal"],
                                "description": "Gmail 消息返回格式。",
                            },
                            "calendar_id": {
                                "type": "string",
                                "description": "日历 ID，默认为 primary。",
                            },
                            "time_min": {"type": "string", "description": "查询起始时间（ISO8601），可留空。"},
                            "time_max": {"type": "string", "description": "查询结束时间（ISO8601），可留空。"},
                            "single_events": {
                                "type": "boolean",
                                "description": "是否展开重复事件，默认为 true。",
                            },
                            "event_summary": {"type": "string", "description": "创建日历事件时的标题。"},
                            "event_description": {"type": "string", "description": "创建日历事件时的说明。"},
                            "event_start": {"type": "string", "description": "事件开始时间（ISO8601）。"},
                            "event_end": {"type": "string", "description": "事件结束时间（ISO8601）。"},
                            "event_attendees": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 16,
                                "description": "事件参与人邮箱列表。",
                            },
                            "email_to": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 16,
                                "description": "邮件收件人列表。",
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
                            "docs_title": {
                                "type": "string",
                                "description": "创建 Google 文档时使用的标题。未提供时会自动生成一个简短标题。",
                            },
                            "docs_content": {
                                "type": "string",
                                "description": "可选。创建文档后要写入的正文内容（纯文本）。",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "skill",
                    "description": "查看可用 skill 目录，或按 slug 读取某个 skill 的正文，用于获取更细的工具/plane 使用策略。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["catalog", "read"]},
                            "slug": {"type": "string", "description": "当 action=read 时填写 skill slug。"},
                            "query": {"type": "string", "description": "当 action=catalog 时可选，用于筛选更相关的 skill。"},
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "plane",
                    "description": (
                        "将复杂任务委派给完整的执行子系统（plane）。"
                        "当前支持 browser plane，由 PinchTab 负责复杂网页登录、导航、滚动和多步网页流程。"
                        "对于复杂网站任务，应优先用 plane，而不是自己微操浏览器动作。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["catalog", "delegate", "status", "continue", "close"],
                            },
                            "plane": {
                                "type": "string",
                                "enum": ["browser"],
                                "description": "当前支持 browser plane。",
                            },
                            "goal": {
                                "type": "string"
                            },
                            "task_id": {
                                "type": "string",
                                "description": "已有 plane 任务的标识，用于 status/continue/close。",
                            },
                            "force_new": {
                                "type": "boolean",
                                "description": "仅在明确需要放弃当前活跃 plane task 并重新开始时才设为 true。",
                            },
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
            return self._tool_context_get(args)
        if tool == "profile":
            return self._tool_profile(args)
        if tool == "memory":
            return self._tool_memory(args)
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
        if tool == "skill":
            return tool_skill(self, args)
        if tool == "plane":
            return tool_plane(self, args)
        if tool == "pinchtab":
            return tool_pinchtab(self, args)
        if tool == "pinchtab_agent":
            return tool_pinchtab_agent(self, args)
        if tool == "pinchtab_session":
            return tool_pinchtab_session(self, args)
        return _result_error(f"unsupported tool: {tool}")

    def _tool_context_get(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()[:400]
        limit = _safe_int(args.get("max_items"), 8, low=1, high=20)
        summary = str(self._memory.get_summary(self.db, self.user_id, workspace=self.workspace) or "")
        focus_items = [
            serialize_focus_item(item)
            for item in self._memory.build_focus_items(self.db, self.user_id, query=query, limit=limit)
        ]
        todos = self._memory.list_todos(
            self.db,
            self.user_id,
            include_done=False,
            limit=limit,
            workspace=self.workspace,
        )
        return _result_ok(
            workspace=self.workspace,
            summary=summary,
            focus_items=focus_items,
            todos=todos,
        )

    def _tool_memory(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "").strip().lower()
        workspace = self.workspace

        if action == "append_fact":
            content = re.sub(r"\s+", " ", str(args.get("content") or "")).strip()
            if not content:
                return _result_error("empty_content")
            self._memory.append_fact_to_memory(user_id=self.user_id, workspace=workspace, content=content)
            return _result_ok(kind="fact", content=content)

        if action == "append_preference":
            content = re.sub(r"\s+", " ", str(args.get("content") or "")).strip()
            if not content:
                return _result_error("empty_content")
            self._memory.append_preference_to_memory(user_id=self.user_id, workspace=workspace, content=content)
            return _result_ok(kind="preference", content=content)

        if action == "add_todo":
            title = re.sub(r"\s+", " ", str(args.get("title") or "")).strip()
            if not title:
                return _result_error("empty_title")
            priority = str(args.get("priority") or "normal").strip().lower() or "normal"
            self._memory.add_todo_to_memory(user_id=self.user_id, workspace=workspace, title=title, priority=priority)
            return _result_ok(kind="todo", title=title, priority=priority)

        return _result_error(f"unsupported_memory_action:{action or 'missing'}")

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
        except Exception as exc:
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
        except Exception as exc:
            return _result_error(f"desktop_open_aelin_failed:{str(exc)[:160]}")
        return _result_ok(
            route=str(result.get("route") or route),
            url=str(result.get("url") or ""),
            opened=bool(result.get("opened", result.get("activated"))),
            detail=str(result.get("detail") or ""),
            summary=f"Aelin 已尝试切换到 {str(result.get('route') or route)[:120]}",
        )

    def _tool_pinchtab(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "").strip().lower()
        startup_error = _ensure_pinchtab_runtime()
        if startup_error is not None:
            return startup_error
        client = get_pinchtab_client()
        if not action:
            return _result_error("missing action")
        if action == "health":
            out = client.health()
            return out if isinstance(out, dict) else _result_error("pinchtab_health_failed")
        if action == "launch_instance":
            inst = client.launch_instance()
            if not bool(inst.get("ok", True)):
                # Fallback: when a fresh instance cannot reach \"running\",
                # try to reuse any existing running instance so that long-
                # lived PinchTab servers remain usable without manual reset.
                fallback = getattr(client, "find_running_instance", None)
                if callable(fallback):
                    reuse = fallback()
                    if bool(reuse.get("ok", True)) and reuse.get("instance_id"):
                        return {
                            "ok": True,
                            "instance_id": str(reuse.get("instance_id") or ""),
                        }
                return inst
            return inst
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

    def _tool_pinchtab_agent(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        High-level browser task helper built on top of PinchTab.

        This is intentionally simple: it launches a fresh instance, asks the LLM
        to propose a short sequence of primitive actions, executes them via
        PinchTab, and returns a compact summary plus any extracted page text.
        """
        goal = str(args.get("goal") or "").strip()
        max_steps = _safe_int(args.get("max_steps"), 4, low=1, high=8)
        # Allow the caller (Aelin) to reuse an existing PinchTab instance/tab so
        # it can分多轮轮询式地推进任务，而不是一次性做完所有步骤。
        instance_id_arg = str(args.get("instance_id") or "").strip()
        tab_id_arg = str(args.get("tab_id") or "").strip()
        if not goal:
            return _result_error("missing goal")
        startup_error = _ensure_pinchtab_runtime()
        if startup_error is not None:
            return startup_error

        service: LLMService | None = getattr(self, "_llm_service", None)
        client = get_pinchtab_client()
        if service is None or getattr(service, "client", None) is None:
            return _result_error("pinchtab_agent_llm_not_configured")

        # Step 1: launch or reuse an instance to operate in.
        if instance_id_arg:
            instance_id = instance_id_arg
        else:
            inst = client.launch_instance()
            if not bool(inst.get("ok", True)):
                # 如果新实例无法在预期时间内就绪，尽量复用现有的运行中实例，
                # 避免因为历史残留实例导致整个浏览任务直接失败。
                fallback = getattr(client, "find_running_instance", None)
                if callable(fallback):
                    reuse = fallback()
                    if bool(reuse.get("ok", True)) and reuse.get("instance_id"):
                        instance_id = str(reuse.get("instance_id") or "").strip()
                    else:
                        return _result_error(str(inst.get("error") or reuse.get("error") or "pinchtab_agent_launch_failed"))
                else:
                    return _result_error(str(inst.get("error") or "pinchtab_agent_launch_failed"))
            else:
                instance_id = str(inst.get("instance_id") or "").strip()
                if not instance_id:
                    # 同样兜底尝试复用现有实例。
                    fallback = getattr(client, "find_running_instance", None)
                    if callable(fallback):
                        reuse = fallback()
                        if bool(reuse.get("ok", True)) and reuse.get("instance_id"):
                            instance_id = str(reuse.get("instance_id") or "").strip()
                if not instance_id:
                    return _result_error("pinchtab_agent_missing_instance_id")

        # Step 2: ask the LLM for a small plan of primitive actions.
        sys_text = (
            "You are a browser task planner for PinchTab. "
            "You control a browser instance via a small set of primitive actions:\n"
            "- open: {\"action\":\"open\",\"url\":\"https://example.com\"}\n"
            "- text: {\"action\":\"text\"}\n"
            "- snapshot: {\"action\":\"snapshot\"}\n"
            "- click: {\"action\":\"click\",\"ref\":\"element-ref\"}\n"
            "Given the user's goal, produce a JSON object with a single key \"steps\" "
            "whose value is an array of action objects (max steps is {max_steps}). "
            "Do not include any other keys or comments. The JSON must be valid. "
            "The browser instance may already be mid-task; plan the *next* short "
            "sequence of actions needed from the current page state."
        ).replace("{max_steps}", str(max_steps))
        user_text = f"goal={goal[:800]}"
        # Planner 调用单独使用较小的超时时间，避免一次规划就占满整个 Agent Loop 的时间窗口。
        planner_timeout = min(float(getattr(service, "timeout_seconds", 30.0) or 30.0), 20.0)
        try:
            response = service.client.chat.completions.create(
                model=service.config.model,
                messages=[
                    {"role": "system", "content": sys_text},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.0,
                max_tokens=256,
                timeout=planner_timeout,
            )
        except Exception as exc:
            return _result_error(f"pinchtab_agent_planner_error:{str(exc)[:120]}")

        choice = response.choices[0] if getattr(response, "choices", None) else None
        message = getattr(choice, "message", None) if choice else None
        content = getattr(message, "content", "") if message else ""
        raw_text = str(content or "")
        plan = _safe_load_json(raw_text)
        if not plan:
            # Be tolerant if the model wraps JSON with explanations; try to
            # extract the first JSON object substring.
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                plan = _safe_load_json(raw_text[start : end + 1])
        raw_steps = plan.get("steps") if isinstance(plan, dict) else None
        steps: list[dict[str, Any]] = [s for s in (raw_steps or []) if isinstance(s, dict)]
        if not steps:
            # Fallback: at least try to open a plausible URL and read text.
            steps = [{"action": "open", "url": "https://www.google.com"}]

        executed: list[dict[str, Any]] = []
        tab_id = tab_id_arg or ""
        last_text = ""
        last_url = ""

        # To避免一次工具调用卡太久，给 pinchtab_agent 一次调用设置一个温和的时间预算，
        # 超过预算就先返回当前进度，由上层决定是否继续调用本工具推进任务。
        started_at = time.perf_counter()
        per_call_budget_s = 25.0
        overall_status = "completed"

        for idx, step in enumerate(steps[:max_steps], start=1):
            if (time.perf_counter() - started_at) > per_call_budget_s:
                # 超过本次调用预算，先返回已完成的步骤，供 Aelin 做下一步决策。
                overall_status = "partial"
                break
            kind = str(step.get("action") or "").strip().lower()
            status = "completed"
            error = ""
            extra: dict[str, Any] = {}
            try:
                if kind == "open":
                    url = str(step.get("url") or "").strip()
                    if not url:
                        raise ValueError("missing url")
                    out = client.open_tab(instance_id=instance_id, url=url)
                    if not bool(out.get("ok")):
                        raise RuntimeError(str(out.get("error") or "open_tab_failed"))
                    tab_id = str(out.get("tab_id") or "").strip() or tab_id
                    last_url = url
                    extra["tab_id"] = tab_id
                    extra["url"] = url
                elif kind == "text":
                    if not tab_id:
                        raise ValueError("missing tab_id for text")
                    out = client.text(tab_id=tab_id)
                    if not bool(out.get("ok", True)):
                        raise RuntimeError(str(out.get("error") or "text_failed"))
                    text_val = str(out.get("text") or "")
                    last_text = text_val
                    last_url = str(out.get("url") or last_url)
                    extra["text_excerpt"] = text_val[:800]
                    extra["url"] = last_url
                elif kind == "snapshot":
                    if not tab_id:
                        raise ValueError("missing tab_id for snapshot")
                    out = client.snapshot(tab_id=tab_id)
                    if not bool(out.get("ok", True)):
                        raise RuntimeError(str(out.get("error") or "snapshot_failed"))
                    extra["title"] = str(out.get("title") or "")
                    extra["url"] = str(out.get("url") or last_url)
                elif kind == "click":
                    if not tab_id:
                        raise ValueError("missing tab_id for click")
                    ref = str(step.get("ref") or "").strip()
                    if not ref:
                        raise ValueError("missing ref")
                    out = client.action(tab_id=tab_id, kind="click", ref=ref)
                    if not bool(out.get("ok", True)):
                        raise RuntimeError(str(out.get("error") or "click_failed"))
                    extra["ref"] = ref
                else:
                    status = "skipped"
                    error = f"unsupported_action:{kind or 'unknown'}"
            except Exception as exc:
                status = "failed"
                error = str(exc)[:160]
            executed.append(
                {
                    "index": idx,
                    "requested": step,
                    "status": status,
                    "error": error,
                    **extra,
                }
            )
            if status == "failed":
                overall_status = "partial"
                break

        login_required = _detect_login_gate(url=last_url, text=last_text)
        summary = f"pinchtab_agent executed {len(executed)} step(s) for goal: {goal[:80]}"
        user_prompt = (
            "检测到目标站点处于登录/验证页面，请你先在浏览器中手动完成登录（含验证码/2FA），"
            "然后回复‘已登录，继续’。"
            if login_required
            else ""
        )
        return _result_ok(
            summary=summary,
            instance_id=instance_id,
            tab_id=tab_id,
            last_url=last_url,
            last_text=last_text[:1200],
            status=overall_status,
            steps=executed,
            requires_user_login=login_required,
            user_prompt=user_prompt,
        )


def _safe_load_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _detect_login_gate(*, url: str, text: str) -> bool:
    hay = f"{str(url or '').lower()}\n{str(text or '').lower()}"
    hints = (
        "x.com/i/flow/login",
        "/login",
        "sign in",
        "log in",
        "登录",
        "登入",
        "验证码",
        "two-factor",
        "2fa",
        "challenge",
    )
    return any(token in hay for token in hints)

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


_PINCHTAB_SESSIONS: dict[str, dict[str, Any]] = {}
# Lightweight mapping from (user_id, workspace) -> latest pinchtab_session id.
# This allows Aelin to恢复并复用上一次浏览器会话，就像人类下次来时
# 还会继续操作同一个浏览器窗口一样。
_PINCHTAB_USER_SESSIONS: dict[tuple[int, str], str] = {}


def get_active_pinchtab_session(user_id: int, workspace: str) -> dict[str, Any] | None:
    """
    Return the latest known PinchTab session snapshot for this user/workspace,
    if any. Used by the agent loop to提示模型“已经有一个可以续上的浏览会话了”。
    """
    key = (int(user_id), str(workspace or "default"))
    sid = _PINCHTAB_USER_SESSIONS.get(key)
    if not sid:
        return None
    sess = _PINCHTAB_SESSIONS.get(sid)
    if not sess:
        return None
    if not _pinchtab_session_belongs_to(sid, sess, user_id=int(user_id), workspace=str(workspace or "default")):
        return None
    return _pinchtab_session_visible_payload(sid, sess)


def _normalize_session_id(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return clean[:64]


def _pinchtab_session_owner_key(*, user_id: int, workspace: str) -> tuple[int, str]:
    return int(user_id), _normalize_workspace(workspace)


def _pinchtab_session_visible_payload(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "instance_id": str(payload.get("instance_id") or ""),
        "tab_id": str(payload.get("tab_id") or ""),
        "last_goal": str(payload.get("last_goal") or ""),
        "last_status": str(payload.get("last_status") or ""),
        "last_url": str(payload.get("last_url") or ""),
        "last_text": str(payload.get("last_text") or ""),
        "last_summary": str(payload.get("last_summary") or ""),
    }


def _pinchtab_session_belongs_to(
    session_id: str,
    payload: dict[str, Any],
    *,
    user_id: int,
    workspace: str,
) -> bool:
    owner_key = _pinchtab_session_owner_key(user_id=user_id, workspace=workspace)
    owner_user_id = payload.get("owner_user_id")
    owner_workspace = str(payload.get("owner_workspace") or "").strip()
    if owner_user_id is None and not owner_workspace:
        return _PINCHTAB_USER_SESSIONS.get(owner_key) == session_id
    try:
        session_owner_user_id = int(owner_user_id)
    except Exception:
        return False
    session_owner_workspace = _normalize_workspace(owner_workspace)
    return (session_owner_user_id, session_owner_workspace) == owner_key


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
                "Only call tools when the user query clearly needs memory/profile/device/screen/browser/attachment operations. "
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


def _execute_pinchtab_session_action(
    self: AelinToolHub,
    *,
    action: str,
    session_id: str = "",
    goal: str = "",
) -> tuple[str, dict[str, Any], str, int]:
    from uuid import uuid4

    action = str(action or "").strip().lower()
    session_id = _normalize_session_id(session_id)
    goal = str(goal or "").strip()

    def _get_session(sid: str) -> dict[str, Any] | None:
        return _PINCHTAB_SESSIONS.get(sid) if sid else None

    def _set_session(sid: str, payload: dict[str, Any]) -> None:
        if not sid:
            return
        _PINCHTAB_SESSIONS[sid] = {
            "owner_user_id": int(self.user_id),
            "owner_workspace": str(self.workspace),
            "instance_id": str(payload.get("instance_id") or payload.get("instance") or ""),
            "tab_id": str(payload.get("tab_id") or ""),
            "last_goal": str(payload.get("goal") or ""),
            "last_status": str(payload.get("status") or ""),
            "last_url": str(payload.get("last_url") or payload.get("url") or ""),
            "last_text": str(payload.get("last_text") or payload.get("text") or ""),
            "last_summary": str(payload.get("summary") or ""),
        }

    started = time.perf_counter()
    status = "completed"
    error = ""

    if action not in {"start", "step", "status", "close"}:
        result = _result_error("unsupported pinchtab_session action")
        return "failed", result, str(result.get("error") or ""), int((time.perf_counter() - started) * 1000)

    if action == "start":
        if not goal:
            result = _result_error("missing goal")
            return "failed", result, str(result.get("error") or ""), int((time.perf_counter() - started) * 1000)
        sid = _normalize_session_id(session_id or f"pinch-{uuid4().hex[:12]}")
        # First step: let pinchtab_agent propose and execute a short plan.
        _, result, error, _ = _execute_tool_call(
            self,
            name="pinchtab_agent",
            args={"goal": goal[:800], "max_steps": 6},
        )
        if not bool(result.get("ok")):
            failed = _result_error(str(result.get("error") or error or "pinchtab_session_start_failed"))
            return "failed", failed, str(failed.get("error") or ""), int((time.perf_counter() - started) * 1000)
        # Persist minimal session state.
        payload = dict(result)
        payload["goal"] = goal
        _set_session(sid, payload)
        # 记录到用户级映射，方便后续对话自动续上这个会话。
        try:
            _PINCHTAB_USER_SESSIONS[_pinchtab_session_owner_key(user_id=self.user_id, workspace=self.workspace)] = sid
        except Exception:
            # 映射失败不应影响工具主流程
            pass
        output = _result_ok(
            session_id=sid,
            **{k: v for k, v in result.items() if k != "ok"},
        )
        return status, output, error, int((time.perf_counter() - started) * 1000)

    # All non-start actions require a valid session.
    sess = _get_session(session_id)
    if sess is None:
        result = _result_error("unknown_session_id")
        return "failed", result, str(result.get("error") or ""), int((time.perf_counter() - started) * 1000)
    if not _pinchtab_session_belongs_to(session_id, sess, user_id=self.user_id, workspace=self.workspace):
        result = _result_error("unknown_session_id")
        return "failed", result, str(result.get("error") or ""), int((time.perf_counter() - started) * 1000)

    if action == "close":
        _PINCHTAB_SESSIONS.pop(session_id, None)
        # 清理用户级映射，如果它正好指向当前会话。
        try:
            key = _pinchtab_session_owner_key(user_id=self.user_id, workspace=self.workspace)
            if _PINCHTAB_USER_SESSIONS.get(key) == session_id:
                _PINCHTAB_USER_SESSIONS.pop(key, None)
        except Exception:
            pass
        return status, _result_ok(session_id=session_id, closed=True), error, int((time.perf_counter() - started) * 1000)

    if action == "status":
        # Return the last known snapshot of this session; no new browser work.
        return status, _result_ok(**_pinchtab_session_visible_payload(session_id, sess)), error, int((time.perf_counter() - started) * 1000)

    # action == "step"
    # Step: continue using the same instance/tab with a refined goal.
    if not goal:
        # If no new goal is provided, reuse last_goal to “继续刚才的任务”。
        goal = str(sess.get("last_goal") or "").strip()
    if not goal:
        result = _result_error("missing goal")
        return "failed", result, str(result.get("error") or ""), int((time.perf_counter() - started) * 1000)

    agent_args = {
        "goal": goal[:800],
        "max_steps": 6,
    }
    if sess.get("instance_id"):
        agent_args["instance_id"] = str(sess["instance_id"])
    if sess.get("tab_id"):
        agent_args["tab_id"] = str(sess["tab_id"])

    _, result, error, _ = _execute_tool_call(
        self,
        name="pinchtab_agent",
        args=agent_args,
    )
    if not bool(result.get("ok")):
        # Planner 或执行失败时，也要把错误状态写回会话，方便 Aelin 观察后决策。
        payload = {
            "instance_id": sess.get("instance_id", ""),
            "tab_id": sess.get("tab_id", ""),
            "goal": goal,
            "status": f"error:{str(result.get('error') or error or 'unknown')[:80]}",
            "summary": str(sess.get("last_summary") or ""),
            "last_url": str(sess.get("last_url") or ""),
            "last_text": str(sess.get("last_text") or ""),
        }
        _set_session(session_id, payload)
        failed = _result_error(str(result.get("error") or error or "pinchtab_session_step_failed"))
        return "failed", failed, str(failed.get("error") or ""), int((time.perf_counter() - started) * 1000)

    payload = dict(result)
    payload["goal"] = goal
    _set_session(session_id, payload)
    # 确保 step 之后也把该会话标记为“当前活跃会话”，便于后续对话续上。
    try:
        _PINCHTAB_USER_SESSIONS[_pinchtab_session_owner_key(user_id=self.user_id, workspace=self.workspace)] = session_id
    except Exception:
        pass
    output = _result_ok(
        session_id=session_id,
        **{k: v for k, v in result.items() if k != "ok"},
    )
    return status, output, error, int((time.perf_counter() - started) * 1000)


def _tool_pinchtab_session(self: AelinToolHub, args: dict[str, Any]) -> dict[str, Any]:
    """
    Legacy session-style wrapper kept for compatibility.

    The browser plane now talks to PinchTab through a dedicated adapter, while
    this tool remains as an internal/compat surface backed by the same runtime.
    """
    _, result, _, latency_ms = _execute_pinchtab_session_action(
        self,
        action=str(args.get("action") or "").strip().lower(),
        session_id=str(args.get("session_id") or "").strip(),
        goal=str(args.get("goal") or "").strip(),
    )
    if isinstance(result, dict) and bool(result.get("ok")):
        result = {**result, "latency_ms": latency_ms}
    return result


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
        elif name in {"profile", "context_get", "device", "screen_get"}:
            if "total" in result:
                note = f"total={result.get('total')}"
            elif "summary" in result:
                note = str(result.get("summary") or "")[:120]
            else:
                note = json.dumps(result, ensure_ascii=False)[:140]
        elif name in {"pinchtab", "pinchtab_agent", "pinchtab_session"}:
            if bool(result.get("requires_user_login")):
                note = str(result.get("user_prompt") or "requires_user_login=true")[:160]
            elif "summary" in result:
                note = str(result.get("summary") or "")[:120]
            else:
                note = json.dumps(result, ensure_ascii=False)[:140]
        else:
            note = json.dumps(result, ensure_ascii=False)[:140]
        lines.append(f"- [{name}/{status}] {note}".strip())
    return lines
