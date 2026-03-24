from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from langchain_openai import ChatOpenAI

from deepagents import create_deep_agent
from deepagents.backends.state import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_core.tools import StructuredTool, Tool
from pydantic import BaseModel, Field

from app.services.aelin.tool_policy import AelinToolPolicy, ToolPolicyUsage
from app.services.aelin.tool_hub import AelinToolHub
from app.services.foundation.llm import LLMService
from app.services.tools.tool_helpers import _result_error
from app.services.tools.tools_device import tool_device, tool_screen_get
from app.services.tools.tools_files import tool_attachment_search
from app.services.tools.tools_gws import tool_google_workspace
from app.services.tools.tools_web import tool_web_search
from app.settings import settings
from app.services.deepagents.cancel_utils import is_cancelled


_log = logging.getLogger(__name__)


class DeepAgentsCancelled(RuntimeError):
    """Raised when the surrounding request has been cancelled."""


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
            "max_results=1..15, fetch_top_k=0..6."
        )
    if name == "attachment_search":
        return (
            "Search uploaded attachments for relevant chunks.\n"
            "Arguments: query=<non-empty string>, attachment_ids?<int[]>, top_k=1..20, "
            "mode=('keyword'|'hybrid')."
        )
    if name == "google_workspace":
        return (
            "Access Google Workspace via local gws CLI.\n"
            "Use action to select runtime/auth/gmail/drive/calendar/docs operations."
        )
    if name == "device":
        return (
            "Desktop actions and status.\n"
            "Allowed actions: 'status', 'open_url', 'open_aelin'."
        )
    if name == "screen_get":
        return "Capture a desktop screenshot for visual inspection."
    return name


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _invoke_tool(
    *,
    name: str,
    args: dict[str, Any],
    handler: Callable[[AelinToolHub, dict[str, Any]], dict[str, Any]],
    tool_hub: AelinToolHub,
    policy: AelinToolPolicy,
    usage: ToolPolicyUsage,
    tool_runs: list[dict[str, Any]],
    cancel_token: Any | None = None,
) -> dict[str, Any]:
    from time import perf_counter

    if is_cancelled(cancel_token):
        raise DeepAgentsCancelled("cancelled")

    decision = policy.evaluate(name=name, args=args, usage=usage)
    call_index = len(tool_runs) + 1
    started = perf_counter()

    if not decision.allowed:
        latency_ms = int((perf_counter() - started) * 1000)
        result = {"ok": False, "error": decision.reason}
        tool_runs.append(
            {
                "call_index": call_index,
                "name": name,
                "args": args,
                "status": "denied",
                "result": result,
                "error": decision.reason,
                "is_write": decision.is_write,
                "latency_ms": latency_ms,
            }
        )
        return result

    if is_cancelled(cancel_token):
        raise DeepAgentsCancelled("cancelled")

    try:
        result = handler(tool_hub, args)
    except Exception as exc:  # noqa: BLE001
        result = _result_error(f"{name}_failed:{str(exc)[:160]}")

    latency_ms = int((perf_counter() - started) * 1000)
    usage.total_calls += 1
    if decision.is_write:
        usage.write_calls += 1
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
            "status": status,
            "result": result,
            "error": error,
            "is_write": decision.is_write,
            "latency_ms": latency_ms,
            "summary": summary,
        }
    )
    return result


def build_chat_tools(
    *,
    tool_hub: AelinToolHub,
    policy: AelinToolPolicy,
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
        handler: Callable[[AelinToolHub, dict[str, Any]], dict[str, Any]],
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
                tool_hub=tool_hub,
                policy=policy,
                usage=usage,
                tool_runs=tool_runs,
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
                tool_hub=tool_hub,
                policy=policy,
                usage=usage,
                tool_runs=tool_runs,
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
                tool_hub=tool_hub,
                policy=policy,
                usage=usage,
                tool_runs=tool_runs,
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
    tool_hub: AelinToolHub,
    policy: AelinToolPolicy,
    memory_summary: str,
    skills_root: Path | None = None,
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
        tool_hub=tool_hub,
        policy=policy,
        cancel_token=cancel_token,
    )

    system_prompt = (
        "You are Aelin running on DeepAgents.\n"
        "Reply in the same language as the user.\n"
        "Use tools only when they materially help.\n"
        "Prefer one correct tool call over repeated partial attempts.\n"
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
    if memory_summary.strip():
        mem_text = memory_summary.strip()
        mem_body = (
            mem_text
            if mem_text.lstrip().startswith("#")
            else "\n".join(
                [
                    "# Aelin Session Memory",
                    "",
                    "## User summary",
                    mem_text,
                ]
            )
        )
        mem_path = "/memory/AGENTS.md"
        memory_files[mem_path] = mem_body
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

