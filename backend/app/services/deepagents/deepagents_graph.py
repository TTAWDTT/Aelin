from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from langchain_openai import ChatOpenAI

from deepagents import create_deep_agent
from deepagents.backends.state import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_core.tools import StructuredTool, Tool
from pydantic import BaseModel, Field

from app.services.deepagents.tool_runtime import (
    ToolCallLimiter,
    ToolPolicyUsage,
    ToolRuntimeContext,
)
from app.services.foundation.llm import LLMService
from app.services.deepagents.input_mapping import build_chat_messages
from app.services.deepagents.output_utils import extract_answer
from app.services.tools.tool_helpers import _result_error
from app.services.tools.tools_device import tool_device, tool_screen_get
from app.services.tools.tools_files import tool_attachment_search
from app.services.tools.tools_gws import tool_google_workspace
from app.services.tools.tools_web import tool_web_search
from app.settings import settings
from app.services.deepagents.cancel_utils import is_cancelled


_log = logging.getLogger(__name__)
_AELIN_TIMEZONE = "Asia/Shanghai"


class DeepAgentsCancelled(RuntimeError):
    """Raised when the surrounding request has been cancelled."""


def _current_date_context() -> str:
    try:
        local_now = datetime.now(ZoneInfo(_AELIN_TIMEZONE))
    except Exception:
        local_now = datetime.now(timezone.utc)
    return (
        f"Current date: {local_now.date().isoformat()}.\n"
        f"Current timezone: {_AELIN_TIMEZONE}.\n"
        f"Current local datetime: {local_now.isoformat(timespec='seconds')}.\n"
        f"Today in {_AELIN_TIMEZONE}: {local_now.strftime('%Y-%m-%d')}.\n"
        "Interpret relative date and time references using the current local datetime above unless a tool result from this run proves otherwise.\n"
        "Do not drift to another year or another date just because retrieved content mentions one."
    )


@dataclass
class DeepAgentsToolRun:
    call_index: int
    name: str
    args: dict[str, Any]
    status: str
    result: dict[str, Any]
    error: str = ""
    is_write: bool = False
    latency_ms: int = 0


@dataclass
class DeepAgentsLoopResult:
    ok: bool
    answer: str
    tool_runs: list[DeepAgentsToolRun] = field(default_factory=list)
    total_calls: int = 0
    write_calls: int = 0
    actions: list[dict[str, str]] = field(default_factory=list)
    error: str = ""
    cancelled: bool = False
    capability_summary: str = ""


class DeviceToolInput(BaseModel):
    action: str = Field(
        ...,
        description="Allowed values: 'status', 'open_url', 'open_aelin'.",
    )
    url: str | None = Field(default=None, description="HTTP(S) URL when action == 'open_url'.")
    route: str | None = Field(default=None, description="Optional route when action == 'open_aelin'.")


class ScreenGetToolInput(BaseModel):
    display_id: str | None = Field(default=None)
    max_edge: int | None = Field(default=1280, description="640-4096.")
    format: str | None = Field(default="jpeg", description="'jpeg' or 'png'.")
    quality: int | None = Field(default=72, description="35-95 for JPEG.")


class WebSearchToolInput(BaseModel):
    action: str = Field(default="search_and_fetch")
    query: str
    max_results: int | None = Field(default=15)
    fetch_top_k: int | None = Field(default=3)


class AttachmentSearchToolInput(BaseModel):
    query: str
    attachment_ids: list[int] | None = Field(default=None)
    top_k: int | None = Field(default=5)
    mode: str | None = Field(default="keyword")


class GoogleWorkspaceToolInput(BaseModel):
    action: str
    calendar_id: str | None = None
    time_min: str | None = None
    time_max: str | None = None
    max_results: int | None = None
    single_events: bool | None = None
    event_summary: str | None = None
    event_description: str | None = None
    event_start: str | None = None
    event_end: str | None = None
    event_attendees: list[str] | None = None
    query: str | None = None
    include_spam_trash: bool | None = None
    message_id: str | None = None
    format: str | None = None
    email_to: list[str] | None = None
    email_cc: list[str] | None = None
    email_bcc: list[str] | None = None
    email_subject: str | None = None
    email_body: str | None = None
    docs_title: str | None = None
    docs_content: str | None = None


def _build_chat_model(service: LLMService, provider: str) -> ChatOpenAI | None:
    """
    Centralised helper to construct the ChatModel used by DeepAgents.

    This keeps all DeepAgents-facing model initialisation in the graph
    assembly module so that both the legacy agent-loop bridge and the new
    native streaming shell share the exact same behaviour.
    """
    try:
        model_name = getattr(service.config, "model", "") or "gpt-4o-mini"
        temperature = float(getattr(service.config, "temperature", 0.0) or 0.0)

        # service.api_key 与 base_url 由 LLMService 统一管理，沿用原有
        # OpenAI-Compatible 策略，这样支持 Nvidia / DeepSeek / 自建 proxy 等。
        api_key = getattr(service, "api_key", None)
        base_url_raw = getattr(service.config, "base_url", "") or ""
        base_url = LLMService._normalize_base_url(base_url_raw) if base_url_raw else None

        if not api_key:
            _log.warning("build_chat_model_missing_api_key provider=%s", provider)
            return None

        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
            http_client=service.create_http_client(),
            timeout=getattr(service, "timeout_seconds", 90.0),
            max_retries=1,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("build_chat_model_failed provider=%s error=%s", provider, str(exc)[:200])
        return None


def _tool_description(name: str) -> str:
    if name == "web_search":
        return (
            "Search the public web.\n"
            "Arguments: action=('search'|'search_and_fetch'), query=<non-empty string>, "
            "max_results=1..15, fetch_top_k=0..6.\n"
            "Never call web_search with an empty query. Do not repeat materially identical queries in the same run. "
            "If one search already returned enough evidence, stop searching and answer."
        )
    if name == "attachment_search":
        return (
            "Search uploaded attachments for relevant chunks.\n"
            "Arguments: query=<non-empty string>, attachment_ids?<int[]>, top_k=1..20, "
            "mode=('keyword'|'hybrid').\n"
            "Do not repeat the same query against the same attachments. If there are no useful hits, say so and stop."
        )
    if name == "google_workspace":
        return (
            "Access Google Workspace via local gws CLI.\n"
            "Use action to select runtime/auth/gmail/drive/calendar/docs operations.\n"
            "Before calling, ensure action-specific required fields are present. Never retry the same write action blindly."
        )
    if name == "device":
        return (
            "Desktop actions and status.\n"
            "Allowed actions: 'status', 'open_url', 'open_aelin'.\n"
            "Use device only when the user explicitly asks for a desktop action such as opening a page or switching the Aelin app.\n"
            "For open_url pass a valid http(s) URL. Do not repeat the same desktop action if it already failed once."
        )
    if name == "screen_get":
        return (
            "Capture a desktop screenshot for visual inspection.\n"
            "Only use when visual evidence is required. Avoid repeated screenshots with the same arguments."
        )
    return name


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _map_tool_runs(raw_tool_runs: list[dict[str, Any]]) -> list[DeepAgentsToolRun]:
    return [
        DeepAgentsToolRun(
            call_index=int(tr.get("call_index", 1)),
            name=str(tr.get("name") or ""),
            args=dict(tr.get("args") or {}),
            status=str(tr.get("status") or ""),
            result=dict(tr.get("result") or {}),
            error=str(tr.get("error") or ""),
            is_write=bool(tr.get("is_write", False)),
            latency_ms=int(tr.get("latency_ms", 0)),
        )
        for tr in raw_tool_runs
    ]


def _parse_capabilities_file(files_mapping: dict[str, Any]) -> dict[str, Any]:
    raw = files_mapping.get("/runtime/capabilities.json")
    if not isinstance(raw, dict):
        return {}
    content = raw.get("content")
    if isinstance(content, list):
        text = "\n".join(str(line) for line in content)
    else:
        text = str(content or "")
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _loop_result(
    *,
    ok: bool,
    answer: str = "",
    tool_runs: list[DeepAgentsToolRun] | None = None,
    total_calls: int = 0,
    write_calls: int = 0,
    actions: list[dict[str, str]] | None = None,
    error: str = "",
    cancelled: bool = False,
    capability_summary: str = "",
) -> DeepAgentsLoopResult:
    return DeepAgentsLoopResult(
        ok=ok,
        answer=answer,
        tool_runs=list(tool_runs or []),
        total_calls=int(total_calls or 0),
        write_calls=int(write_calls or 0),
        actions=list(actions or []),
        error=error,
        cancelled=cancelled,
        capability_summary=capability_summary,
    )


def _emit_tool_event(
    callback: Callable[[dict[str, Any]], None] | None,
    payload: dict[str, Any],
) -> None:
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:
        pass


def _invoke_tool(
    *,
    name: str,
    args: dict[str, Any],
    handler: Callable[[ToolRuntimeContext, dict[str, Any]], dict[str, Any]],
    context: ToolRuntimeContext,
    limiter: ToolCallLimiter,
    usage: ToolPolicyUsage,
    tool_runs: list[dict[str, Any]],
    tool_event_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> dict[str, Any]:
    from time import perf_counter

    if is_cancelled(cancel_token):
        raise DeepAgentsCancelled("cancelled")

    decision = limiter.evaluate(name=name, args=args, usage=usage)
    call_index = len(tool_runs) + 1
    started = perf_counter()

    if not decision.allowed:
        latency_ms = int((perf_counter() - started) * 1000)
        result = {"ok": False, "error": decision.reason}
        usage.note_denial()
        tool_key = f"{name}:{call_index}"
        tool_runs.append(
            {
                "call_index": call_index,
                "name": name,
                "args": args,
                "key": tool_key,
                "status": "denied",
                "result": result,
                "error": decision.reason,
                "is_write": decision.is_write,
                "latency_ms": latency_ms,
                "summary": f"{name} denied: {decision.reason[:160]}",
            }
        )
        _emit_tool_event(
            tool_event_cb,
            {
                "key": tool_key,
                "name": name,
                "args": args,
                "state": "denied",
                "result": result,
                "error": decision.reason,
                "is_write": decision.is_write,
                "latency_ms": latency_ms,
            },
        )
        return result

    if is_cancelled(cancel_token):
        raise DeepAgentsCancelled("cancelled")

    usage.note_invocation(name, args)
    tool_key = f"{name}:{call_index}"
    _emit_tool_event(
        tool_event_cb,
        {
            "key": tool_key,
            "name": name,
            "args": args,
            "state": "running",
            "result": {},
            "error": "",
            "is_write": decision.is_write,
            "latency_ms": 0,
        },
    )
    result: dict[str, Any]
    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def _run_handler() -> None:
        try:
            result_box["value"] = handler(context, args)
        except BaseException as exc:  # noqa: BLE001
            error_box["value"] = exc

    timeout_seconds = max(
        1.0,
        float(getattr(settings, "deepagents_tool_timeout_seconds", 25.0) or 25.0),
    )
    worker = threading.Thread(target=_run_handler, daemon=True)
    worker.start()
    wait_slice_seconds = 0.5
    heartbeat_interval_seconds = 3.0
    last_heartbeat_at = started
    cancelled_midflight = False
    deadline = started + timeout_seconds

    while worker.is_alive():
        now = perf_counter()
        remaining = deadline - now
        if remaining <= 0:
            break
        worker.join(timeout=min(wait_slice_seconds, remaining))
        if not worker.is_alive():
            break
        if is_cancelled(cancel_token):
            cancelled_midflight = True
            break
        current = perf_counter()
        if current - last_heartbeat_at >= heartbeat_interval_seconds:
            _emit_tool_event(
                tool_event_cb,
                {
                    "key": tool_key,
                    "name": name,
                    "args": args,
                    "state": "running",
                    "result": {},
                    "error": "",
                    "is_write": decision.is_write,
                    "latency_ms": int((current - started) * 1000),
                },
            )
            last_heartbeat_at = current

    if cancelled_midflight:
        result = _result_error(
            f"{name}_cancelled: request cancelled while tool was running"
        )
    elif worker.is_alive():
        result = _result_error(
            f"{name}_timeout: tool exceeded {int(timeout_seconds)}s; adjust arguments once or stop using this tool and answer from current evidence"
        )
    elif "value" in error_box:
        result = _result_error(f"{name}_failed:{str(error_box['value'])[:160]}")
    else:
        raw_result = result_box.get("value")
        if isinstance(raw_result, dict):
            result = raw_result
        else:
            result = _result_error(f"{name}_failed:tool returned invalid payload")

    latency_ms = int((perf_counter() - started) * 1000)
    usage.total_calls += 1
    if decision.is_write:
        usage.write_calls += 1
    usage.note_result(result)
    if cancelled_midflight:
        status = "cancelled"
    else:
        status = "completed" if bool(result.get("ok", True)) else "failed"
    error = "" if status == "completed" else str(result.get("error") or "")[:160]

    # Provide a compact, human-friendly summary string for UI/trace rendering.
    summary = ""
    if error:
        summary = f"{name} error: {error}"
    else:
        # Prefer an explicit summary from the tool result when present.
        try:
            summary_field = str(result.get("summary") or "").strip()
        except Exception:
            summary_field = ""
        if summary_field:
            summary = f"{name}: {summary_field[:160]}"
        else:
            scope = ""
            try:
                scope = str(result.get("scope") or "")[:80]
            except Exception:
                scope = ""
            if scope:
                summary = f"{name} -> {scope}"
            else:
                total = result.get("total")
                if isinstance(total, int):
                    summary = f"{name} total={total}"
                else:
                    summary = f"{name}({len(args)} args)"

    tool_runs.append(
        {
            "call_index": call_index,
            "name": name,
            "args": args,
            "key": tool_key,
            "status": status,
            "result": result,
            "error": error,
            "is_write": decision.is_write,
            "latency_ms": latency_ms,
            "summary": summary,
        }
    )
    _emit_tool_event(
        tool_event_cb,
        {
            "key": tool_key,
            "name": name,
            "args": args,
            "state": status,
            "result": result,
            "error": error,
            "is_write": decision.is_write,
            "latency_ms": latency_ms,
            "summary": summary,
        },
    )
    return result


def build_chat_tools(
    *,
    context: ToolRuntimeContext,
    limiter: ToolCallLimiter,
    tool_event_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> tuple[list[Tool], list[dict[str, Any]], ToolPolicyUsage]:
    """
    Build the DeepAgents-facing tool list using explicit tool registration.

    This file is intentionally the assembly layer only: it wires Aelin's
    capability functions into DeepAgents/LangChain tools, applies tool policy,
    and records tool runs for UI/debugging.
    """
    usage = ToolPolicyUsage()
    tool_runs: list[dict[str, Any]] = []

    def _make_structured_tool(
        name: str,
        handler: Callable[[ToolRuntimeContext, dict[str, Any]], dict[str, Any]],
        args_schema: type[BaseModel],
        arg_names: list[str],
    ) -> Tool:
        def _call_tool(**kwargs: Any) -> dict[str, Any]:
            args = {
                key: value
                for key, value in kwargs.items()
                if key in arg_names and value is not None
            }
            return _invoke_tool(
                name=name,
                args=args,
                handler=handler,
                context=context,
                limiter=limiter,
                usage=usage,
                tool_runs=tool_runs,
                tool_event_cb=tool_event_cb,
                cancel_token=cancel_token,
            )

        return StructuredTool.from_function(
            func=_call_tool,
            name=name,
            description=_tool_description(name),
            args_schema=args_schema,
        )

    def _make_device_tool() -> Tool:
        def _run_device(action: str, url: str | None = None, route: str | None = None) -> dict[str, Any]:
            args: dict[str, Any] = {"action": str(action or "").strip()}
            if url is not None and str(url).strip():
                args["url"] = str(url).strip()
            if route is not None and str(route).strip():
                args["route"] = str(route).strip()
            return _invoke_tool(
                name="device",
                args=args,
                handler=tool_device,
                context=context,
                limiter=limiter,
                usage=usage,
                tool_runs=tool_runs,
                tool_event_cb=tool_event_cb,
                cancel_token=cancel_token,
            )

        return StructuredTool.from_function(
            func=_run_device,
            name="device",
            description=_tool_description("device"),
            args_schema=DeviceToolInput,
        )

    def _make_screen_get_tool() -> Tool:
        def _run_screen_get(
            display_id: str | None = None,
            max_edge: int | None = None,
            format: str | None = None,  # noqa: A002 - keep external arg name stable
            quality: int | None = None,
        ) -> dict[str, Any]:
            args: dict[str, Any] = {}
            if display_id is not None and str(display_id).strip():
                args["display_id"] = str(display_id).strip()
            if max_edge is not None:
                try:
                    args["max_edge"] = int(max_edge)
                except Exception:
                    pass
            if format is not None and str(format).strip():
                args["format"] = str(format).strip()
            if quality is not None:
                try:
                    args["quality"] = int(quality)
                except Exception:
                    pass
            return _invoke_tool(
                name="screen_get",
                args=args,
                handler=tool_screen_get,
                context=context,
                limiter=limiter,
                usage=usage,
                tool_runs=tool_runs,
                tool_event_cb=tool_event_cb,
                cancel_token=cancel_token,
            )

        return StructuredTool.from_function(
            func=_run_screen_get,
            name="screen_get",
            description=_tool_description("screen_get"),
            args_schema=ScreenGetToolInput,
        )

    tools: list[Tool] = [
        _make_structured_tool(
            "web_search",
            tool_web_search,
            WebSearchToolInput,
            ["action", "query", "max_results", "fetch_top_k"],
        ),
        _make_structured_tool(
            "attachment_search",
            tool_attachment_search,
            AttachmentSearchToolInput,
            ["query", "attachment_ids", "top_k", "mode"],
        ),
        _make_structured_tool(
            "google_workspace",
            tool_google_workspace,
            GoogleWorkspaceToolInput,
            [
                "action",
                "calendar_id",
                "time_min",
                "time_max",
                "max_results",
                "single_events",
                "event_summary",
                "event_description",
                "event_start",
                "event_end",
                "event_attendees",
                "query",
                "include_spam_trash",
                "message_id",
                "format",
                "email_to",
                "email_cc",
                "email_bcc",
                "email_subject",
                "email_body",
                "docs_title",
                "docs_content",
            ],
        ),
        _make_device_tool(),
        _make_screen_get_tool(),
    ]
    return tools, tool_runs, usage


def build_chat_agent(
    *,
    service: LLMService,
    provider: str,
    context: ToolRuntimeContext,
    limiter: ToolCallLimiter,
    memory_text: str,
    skills_root: Path | None = None,
    tool_event_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> tuple[Any, ToolPolicyUsage, list[dict[str, Any]], dict[str, Any]]:
    """
    Construct a DeepAgents chat agent along with tool usage trackers and
    virtual file mounts for skills + AGENTS.md memory.
    """
    chat_model = _build_chat_model(service, provider)
    if chat_model is None:
        return None, ToolPolicyUsage(), [], {}

    tools, tool_runs, usage = build_chat_tools(
        context=context,
        limiter=limiter,
        tool_event_cb=tool_event_cb,
        cancel_token=cancel_token,
    )

    system_prompt = (
        "You are Aelin running on DeepAgents.\n"
        "Reply in the same language as the user.\n"
        "Use tools only when they materially help.\n"
        "Prefer one correct tool call over repeated partial attempts.\n"
        "Before calling any tool, first form a complete and valid argument set.\n"
        "If a tool call is rejected for missing or invalid arguments, correct the arguments once instead of retrying blindly.\n"
        "Do not repeat materially identical tool calls in the same run unless new evidence changes the request.\n"
        "If two recent tool attempts failed or produced no new information, stop using tools and answer from the current evidence.\n"
        "When a tool is unavailable, unauthorized, times out, or returns no useful information, say that clearly and move on.\n"
        "Tool-specific rules:\n"
        "- web_search: always provide a non-empty query; avoid repeated near-duplicate queries; stop once you have enough evidence.\n"
        "- attachment_search: search with a concrete query and available attachment ids only; do not repeat the same attachment search.\n"
        "- google_workspace: choose a concrete action and include all required fields before calling; never blindly retry writes.\n"
        "- device: only use status/open_url/open_aelin when the user explicitly asks for desktop or browser navigation; open_url requires a valid http(s) URL.\n"
        "- screen_get: capture only when visual evidence is necessary; avoid repeated screenshots with the same arguments.\n"
        f"{_current_date_context()}\n"
        "If the user asks about date-sensitive facts, keep the answer explicitly grounded to the current date context above.\n"
        "If search results contain stale dates, say that clearly instead of silently treating them as current.\n"
        "Consult /runtime/capabilities.json for the exact tools, skills, and memory files mounted in this run.\n"
        "Treat /memory/AGENTS.md as the canonical long-term memory file.\n"
        "Read skills on demand from /skills/... when a matching skill is relevant.\n"
        "Never claim you searched, opened, read, or cited an external source unless the corresponding tool call succeeded in this run.\n"
        "If a required tool or skill is unavailable, say so explicitly instead of implying the action completed."
    )

    skills_root = skills_root or (_backend_root() / "deepagents_skills")
    skill_files: dict[str, str] = {}
    skill_sources: list[str] = []
    mounted_skills: list[str] = []

    def _mount_skills_from_root(root: Path, virtual_root: str) -> None:
        nonlocal skill_files, skill_sources, mounted_skills

        if not root.is_dir():
            return

        has_any = False
        for subdir in root.iterdir():
            if not subdir.is_dir():
                continue
            skill_md = subdir / "SKILL.md"
            if not skill_md.is_file():
                continue

            skill_dir_name = subdir.name.replace("_", "-")
            virtual_dir = f"{virtual_root}{skill_dir_name}/"
            mounted_any_file = False
            for file_path in subdir.rglob("*"):
                if not file_path.is_file():
                    continue
                try:
                    text = file_path.read_text(encoding="utf-8")
                except Exception:
                    continue
                relative_path = file_path.relative_to(subdir).as_posix()
                skill_files[f"{virtual_dir}{relative_path}"] = text
                mounted_any_file = True

            if mounted_any_file:
                has_any = True
                mounted_skills.append(f"{virtual_root}{skill_dir_name}/")

        if has_any and virtual_root not in skill_sources:
            skill_sources.append(virtual_root)

    _mount_skills_from_root(skills_root, "/skills/aelin/")

    extra_dir = str(getattr(settings, "deepagents_extra_skills_dir", "") or "").strip()
    if extra_dir:
        _mount_skills_from_root(Path(extra_dir), "/skills/external/")

    memory_files: dict[str, str] = {}
    memory_paths: list[str] = []
    if memory_text.strip():
        mem_path = "/memory/AGENTS.md"
        memory_files[mem_path] = memory_text.strip()
        memory_paths.append(mem_path)

    files: dict[str, Any] = {}
    for path, text in {**skill_files, **memory_files}.items():
        files[path] = create_file_data(text)
    files["/runtime/capabilities.json"] = create_file_data(
        json.dumps(
            {
                "tools": [tool.name for tool in tools],
                "skill_sources": skill_sources,
                "mounted_skills": mounted_skills,
                "memory_files": memory_paths,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    agent = create_deep_agent(
        model=chat_model,
        system_prompt=system_prompt,
        backend=StateBackend,
        tools=tools,
        skills=skill_sources or None,
        memory=memory_paths or None,
    )
    return agent, usage, tool_runs, files


def run_deepagents_loop(
    *,
    service: LLMService,
    provider: str,
    context: ToolRuntimeContext,
    limiter: ToolCallLimiter,
    query: str,
    memory_text: str,
    history_turns: list[dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
    cancel_token: Any | None = None,
) -> DeepAgentsLoopResult:
    try:
        if is_cancelled(cancel_token):
            raise DeepAgentsCancelled("cancelled")

        agent, usage, raw_tool_runs, files_mapping = build_chat_agent(
            service=service,
            provider=provider,
            context=context,
            limiter=limiter,
            memory_text=memory_text,
            cancel_token=cancel_token,
        )
        if agent is None:
            return _loop_result(ok=False, error="llm_not_configured")

        capabilities = _parse_capabilities_file(files_mapping)
        capability_summary = (
            f"tools={len(list(capabilities.get('tools') or []))}; "
            f"skills={len(list(capabilities.get('mounted_skills') or []))}; "
            f"memory_files={len(list(capabilities.get('memory_files') or []))}"
        )

        invoke_payload = {
            "messages": build_chat_messages(
                query=query,
                history_turns=history_turns,
                images=images,
            )
        }
        if files_mapping:
            invoke_payload["files"] = dict(files_mapping)

        if is_cancelled(cancel_token):
            raise DeepAgentsCancelled("cancelled")
        response = agent.invoke(invoke_payload)
        if is_cancelled(cancel_token):
            raise DeepAgentsCancelled("cancelled")

        answer = extract_answer(response).strip()
        tool_runs = _map_tool_runs(raw_tool_runs)

        if not answer:
            return _loop_result(
                ok=False,
                tool_runs=tool_runs,
                total_calls=getattr(usage, "total_calls", 0),
                write_calls=getattr(usage, "write_calls", 0),
                error="empty_answer_from_deepagents",
                capability_summary=capability_summary,
            )

        return _loop_result(
            ok=True,
            answer=answer,
            tool_runs=tool_runs,
            total_calls=getattr(usage, "total_calls", 0),
            write_calls=getattr(usage, "write_calls", 0),
            capability_summary=capability_summary,
        )
    except DeepAgentsCancelled:
        return _loop_result(ok=False, cancelled=True, error="cancelled")
    except Exception as exc:  # noqa: BLE001
        _log.exception("deepagents_unhandled_error provider=%s", provider)
        return _loop_result(
            ok=False,
            error=f"deepagents_unhandled_error:{str(exc)[:160]}",
        )

