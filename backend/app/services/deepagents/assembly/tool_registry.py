from __future__ import annotations

from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable

from langchain_core.tools import StructuredTool, Tool
from pydantic import BaseModel, Field

from app.services.deepagents.assembly.output_mapping import DeepAgentsCancelled
from app.services.deepagents.assembly.prompt import tool_description
from app.services.deepagents.cancel_utils import is_cancelled
from app.services.deepagents.tool_runtime import (
    _acquire_tool_executor_slot,
    _submit_tool_future,
    ToolCallLimiter,
    ToolPolicyUsage,
    ToolRuntimeContext,
)
from app.services.tools.tool_helpers import _result_error
from app.services.tools.tools_device import tool_device, tool_screen_get
from app.services.tools.tools_execute import tool_execute
from app.services.tools.tools_files import tool_attachment_search
from app.services.tools.tools_gws import tool_google_workspace
from app.services.tools.tools_present_files import tool_present_files
from app.services.tools.tools_web import tool_web_search
from app.settings import settings


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


class ExecuteToolInput(BaseModel):
    command: str = Field(..., description="Non-interactive shell command to execute.")
    shell: str | None = Field(
        default=None,
        description="Optional shell override. On Windows use 'cmd' or 'powershell'.",
    )
    cwd: str | None = Field(
        default=None,
        description="Optional working directory inside the allowed local workspace roots.",
    )
    timeout_ms: int | None = Field(
        default=None,
        description="Optional timeout in milliseconds (1000-120000).",
    )


class PresentFilesToolInput(BaseModel):
    filepaths: list[str] = Field(
        ...,
        description="Final deliverable file paths. Only files under /outputs or the mapped outputs directory can be presented.",
    )


def _invoke_tool(
    *,
    name: str,
    args: dict[str, Any],
    handler: Callable[[ToolRuntimeContext, dict[str, Any]], dict[str, Any]],
    context: ToolRuntimeContext,
    limiter: ToolCallLimiter,
    usage: ToolPolicyUsage,
    tool_runs: list[dict[str, Any]],
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
        return result

    if is_cancelled(cancel_token):
        raise DeepAgentsCancelled("cancelled")

    slot = _acquire_tool_executor_slot()
    if slot is None:
        latency_ms = int((perf_counter() - started) * 1000)
        result = {
            "ok": False,
            "error": (
                f"{name}_busy: previous long-running tool calls are still draining; "
                "stop using tools for now and answer from current evidence"
            ),
            "stop_retry": True,
        }
        if decision.is_write:
            result["maybe_applied"] = True
        usage.note_denial()
        tool_key = f"{name}:{call_index}"
        tool_runs.append(
            {
                "call_index": call_index,
                "name": name,
                "args": args,
                "key": tool_key,
                "status": "busy",
                "result": result,
                "error": str(result["error"]),
                "is_write": decision.is_write,
                "latency_ms": latency_ms,
                "summary": f"{name} busy: prior tool calls are still draining",
            }
        )
        return result

    executor, semaphore = slot

    usage.note_invocation(name, args)
    tool_key = f"{name}:{call_index}"
    result: dict[str, Any]
    future = _submit_tool_future(executor, semaphore, handler, context, args)

    timeout_seconds = max(
        1.0,
        float(getattr(settings, "deepagents_tool_timeout_seconds", 25.0) or 25.0),
    )
    wait_slice_seconds = 0.5
    cancelled_midflight = False
    deadline = started + timeout_seconds

    while not future.done():
        now = perf_counter()
        remaining = deadline - now
        if remaining <= 0:
            break
        try:
            future.result(timeout=min(wait_slice_seconds, remaining))
        except FutureTimeout:
            pass
        except BaseException:
            break
        if future.done():
            break
        if is_cancelled(cancel_token):
            cancelled_midflight = True
            break

    if cancelled_midflight:
        result = _result_error(
            f"{name}_cancelled: request cancelled while tool was running"
        )
        result["stop_retry"] = True
        if decision.is_write:
            result["maybe_applied"] = True
            result["error"] = (
                f"{name}_cancelled: request cancelled while the write tool was running; "
                "the operation may still complete in the background, so do not retry the same write blindly"
            )
    elif not future.done():
        result = _result_error(
            f"{name}_timeout: tool exceeded {int(timeout_seconds)}s; "
            "stop using this tool in this run and answer from current evidence"
        )
        result["stop_retry"] = True
        if decision.is_write:
            result["maybe_applied"] = True
            result["error"] = (
                f"{name}_timeout: tool exceeded {int(timeout_seconds)}s; "
                "the write may still complete in the background, so do not retry the same write blindly"
            )
    else:
        try:
            raw_result = future.result()
        except BaseException as exc:  # noqa: BLE001
            result = _result_error(f"{name}_failed:{str(exc)[:160]}")
        else:
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

    summary = ""
    if error:
        summary = f"{name} error: {error}"
    else:
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
    return result


def build_chat_tools(
    *,
    context: ToolRuntimeContext,
    limiter: ToolCallLimiter,
    cancel_token: Any | None = None,
) -> tuple[list[Tool], list[dict[str, Any]], ToolPolicyUsage]:
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
                cancel_token=cancel_token,
            )

        return StructuredTool.from_function(
            func=_call_tool,
            name=name,
            description=tool_description(name),
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
                cancel_token=cancel_token,
            )

        return StructuredTool.from_function(
            func=_run_device,
            name="device",
            description=tool_description("device"),
            args_schema=DeviceToolInput,
        )

    def _make_screen_get_tool() -> Tool:
        def _run_screen_get(
            display_id: str | None = None,
            max_edge: int | None = None,
            format: str | None = None,  # noqa: A002
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
                cancel_token=cancel_token,
            )

        return StructuredTool.from_function(
            func=_run_screen_get,
            name="screen_get",
            description=tool_description("screen_get"),
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
        _make_structured_tool(
            "present_files",
            tool_present_files,
            PresentFilesToolInput,
            ["filepaths"],
        ),
    ]
    if bool(getattr(settings, "desktop_plugin_execute_enabled", False)):
        tools.append(
            _make_structured_tool(
                "execute",
                tool_execute,
                ExecuteToolInput,
                ["command", "shell", "cwd", "timeout_ms"],
            )
        )
    return tools, tool_runs, usage
