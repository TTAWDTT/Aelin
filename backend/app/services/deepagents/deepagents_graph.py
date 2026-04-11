from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx
from langchain_openai import ChatOpenAI

try:
    from deepagents import create_deep_agent
    from deepagents.backends.filesystem import FilesystemBackend
    from deepagents.backends.state import StateBackend
    from deepagents.backends.utils import create_file_data
except Exception:  # pragma: no cover - fallback for test environments without deepagents
    @dataclass
    class _FallbackDownloadResponse:
        content: bytes | None = None

    class _FallbackAgent:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = dict(kwargs or {})

        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            _ = payload
            return {"answer": ""}

        async def astream(self, *_args: Any, **_kwargs: Any):
            if False:
                yield None

        def get_graph(self) -> dict[str, Any]:
            return {}

    def create_deep_agent(**kwargs: Any) -> Any:
        return _FallbackAgent(**kwargs)

    def create_file_data(content: str) -> dict[str, Any]:
        text = str(content or "")
        lines = text.splitlines()
        if text and not lines:
            lines = [text]
        return {
            "content": lines,
            "created_at": "",
            "modified_at": "",
        }

    class StateBackend:
        def __init__(self, runtime: Any) -> None:
            self.runtime = runtime

        def _files(self) -> dict[str, dict[str, Any]]:
            state = getattr(self.runtime, "state", None)
            if not isinstance(state, dict):
                state = {}
                setattr(self.runtime, "state", state)
            files = state.get("files")
            if not isinstance(files, dict):
                files = {}
                state["files"] = files
            return files

        def write(self, file_path: str, content: str) -> Any:
            from app.services.deepagents.managed_backend import WriteResult

            self._files()[str(file_path)] = create_file_data(content)
            return WriteResult(path=str(file_path), error=None)

        async def awrite(self, file_path: str, content: str) -> Any:
            return self.write(file_path, content)

        def download_files(self, paths: list[str]) -> list[Any]:
            files = self._files()
            responses: list[_FallbackDownloadResponse] = []
            for path in list(paths or []):
                entry = files.get(str(path)) or {}
                content = entry.get("content")
                if isinstance(content, list):
                    text = "\n".join(str(line) for line in content)
                else:
                    text = str(content or "")
                responses.append(_FallbackDownloadResponse(content=text.encode("utf-8")))
            return responses

        def ls_info(self, path: str) -> list[dict[str, Any]]:
            prefix = str(path or "")
            files = self._files()
            out: list[dict[str, Any]] = []
            for file_path in sorted(files.keys()):
                if file_path.startswith(prefix):
                    out.append({"path": file_path, "is_dir": False})
            return out

    class FilesystemBackend:
        def __init__(self, *, root_dir: Path, virtual_mode: bool = True) -> None:
            self.root_dir = Path(root_dir)
            self.virtual_mode = bool(virtual_mode)
            self._route_prefix = "/"

        def set_route_prefix(self, prefix: str) -> None:
            self._route_prefix = str(prefix or "/")

        def _relative_path(self, path: str) -> Path:
            normalized = str(path or "")
            prefix = str(self._route_prefix or "/")
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
            normalized = normalized.lstrip("/").replace("\\", "/")
            return self.root_dir / normalized

        def write(self, file_path: str, content: str) -> Any:
            from app.services.deepagents.managed_backend import WriteResult

            target = self._relative_path(file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content or ""), encoding="utf-8")
            return WriteResult(path=str(file_path), error=None)

        async def awrite(self, file_path: str, content: str) -> Any:
            return self.write(file_path, content)

        def download_files(self, paths: list[str]) -> list[Any]:
            responses: list[_FallbackDownloadResponse] = []
            for path in list(paths or []):
                target = self._relative_path(path)
                data = target.read_bytes() if target.is_file() else None
                responses.append(_FallbackDownloadResponse(content=data))
            return responses

        def ls_info(self, path: str) -> list[dict[str, Any]]:
            target = self._relative_path(path)
            base = target if target.is_dir() else target.parent
            if not base.exists():
                return []
            entries: list[dict[str, Any]] = []
            for child in sorted(base.iterdir(), key=lambda item: item.name):
                relative = child.relative_to(self.root_dir).as_posix()
                virtual_path = f"{self._route_prefix.rstrip('/')}/{relative}"
                if child.is_dir():
                    virtual_path = f"{virtual_path.rstrip('/')}/"
                entries.append({"path": virtual_path, "is_dir": child.is_dir()})
            return entries
from langchain_core.tools import StructuredTool, Tool
from pydantic import BaseModel, Field

from app.services.deepagents.managed_backend import ManagedCompositeBackend
from app.services.deepagents.model_timeout_middleware import (
    DeepAgentsModelTimeoutMiddleware,
    DeepAgentsToolMessageSanitizerMiddleware,
)
from app.services.deepagents.tool_runtime import (
    _acquire_tool_executor_slot,
    _submit_tool_future,
    ToolCallLimiter,
    ToolPolicyUsage,
    ToolRuntimeContext,
)
from app.services.foundation.llm import LLMService
from app.services.deepagents.input_mapping import build_chat_messages
from app.services.deepagents.output_utils import extract_answer
from app.services.tools.tool_helpers import _result_error
from app.services.tools.tools_device import tool_device, tool_screen_get
from app.services.tools.tools_execute import tool_execute
from app.services.tools.tools_files import tool_attachment_search
from app.services.tools.tools_gws import tool_google_workspace
from app.services.tools.tools_memory import tool_memory_search
from app.services.tools.tools_web import tool_web_search
from app.settings import settings
from app.services.deepagents.cancel_utils import is_cancelled


_log = logging.getLogger(__name__)
_AELIN_TIMEZONE = "Asia/Shanghai"
_SKILL_MOUNT_CACHE_LOCK = threading.Lock()
_SKILL_MOUNT_CACHE: dict[tuple[str, str], "SkillMountSnapshot"] = {}


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


@dataclass(frozen=True)
class SkillMountSnapshot:
    skill_sources: list[str]
    mounted_skills: list[str]


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


class MemorySearchToolInput(BaseModel):
    query: str
    top_k: int | None = Field(default=6)
    kinds: list[str] | None = Field(default=None)


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
    cwd: str | None = Field(
        default=None,
        description="Optional working directory inside the allowed local workspace roots.",
    )
    timeout_ms: int | None = Field(
        default=None,
        description="Optional timeout in milliseconds (1000-120000).",
    )


def _build_deepagents_http_timeout(service: LLMService) -> httpx.Timeout:
    request_timeout = max(5.0, float(getattr(service, "timeout_seconds", 90.0) or 90.0))
    read_timeout = max(
        5.0,
        float(getattr(settings, "deepagents_stream_idle_timeout_seconds", request_timeout) or request_timeout),
    )
    effective_read_timeout = min(request_timeout, read_timeout)
    return httpx.Timeout(
        connect=request_timeout,
        read=effective_read_timeout,
        write=request_timeout,
        pool=request_timeout,
    )


def _build_agent_middleware() -> list[Any]:
    middleware: list[Any] = [
        DeepAgentsToolMessageSanitizerMiddleware(),
    ]
    timeout_seconds = float(getattr(settings, "deepagents_run_timeout_seconds", 75.0) or 0.0)
    if timeout_seconds > 0:
        middleware.append(
            DeepAgentsModelTimeoutMiddleware(
                timeout_seconds=timeout_seconds,
                retry_attempts=int(getattr(settings, "deepagents_model_retry_attempts", 2) or 0),
                retry_backoff_seconds=float(
                    getattr(settings, "deepagents_model_retry_backoff_seconds", 0.35) or 0.0
                ),
            )
        )
    return middleware


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

        http_timeout = _build_deepagents_http_timeout(service)
        verify_ssl = LLMService.resolve_verify_ssl(getattr(service, "config", None))
        request_timeout = max(5.0, float(getattr(service, "timeout_seconds", 90.0) or 90.0))

        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(
                verify=verify_ssl,
                follow_redirects=True,
                timeout=http_timeout,
            ),
            http_async_client=httpx.AsyncClient(
                verify=verify_ssl,
                follow_redirects=True,
                timeout=http_timeout,
            ),
            timeout=request_timeout,
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
            "attachment_ids is optional when this run already provides available_attachment_ids in /runtime/capabilities.json; "
            "the runtime will use those scoped ids automatically.\n"
            "Always provide a concrete non-empty query that reflects what information you need from the files "
            "(for example 'project codename deadline deliverables').\n"
            "Do not repeat the same query against the same attachments. If there are no useful hits, say so and stop."
        )
    if name == "memory_search":
        return (
            "Search long-term memory without injecting the entire memory corpus into the prompt.\n"
            "Arguments: query=<non-empty string>, top_k=1..20, kinds?<string[]>.\n"
            "Use before opening /memory/*.md files when you need past preferences, facts, projects, or recent context.\n"
            "Prefer one focused query over repeated vague retries."
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
    if name == "execute":
        return (
            "Execute a non-interactive shell command on the local desktop runtime.\n"
            "Arguments: command=<non-empty string>, cwd?<allowed directory>, timeout_ms=1000..120000.\n"
            "Use for coding or inspection tasks like running tests, listing files, or checking git status.\n"
            "Avoid interactive commands, long-running dev servers, or commands that wait for user input."
        )
    return name


def _backend_root() -> Path:
    return Path(__file__).parent.parent.parent.parent


def _build_skill_mount_snapshot(skills_root: Path, extra_dir: str) -> SkillMountSnapshot:
    skill_sources: list[str] = []
    mounted_skills: list[str] = []

    def _mount_skills_from_root(root: Path, virtual_root: str) -> None:
        nonlocal skill_sources, mounted_skills

        if not root.is_dir():
            return

        has_any = False
        for subdir in root.iterdir():
            if not subdir.is_dir():
                continue
            skill_md = subdir / "SKILL.md"
            if not skill_md.is_file():
                continue

            has_any = True
            mounted_skills.append(f"{virtual_root}{subdir.name}/")

        if has_any and virtual_root not in skill_sources:
            skill_sources.append(virtual_root)

    _mount_skills_from_root(skills_root, "/skills/aelin/")
    if extra_dir:
        _mount_skills_from_root(Path(extra_dir), "/skills/external/")

    return SkillMountSnapshot(
        skill_sources=list(skill_sources),
        mounted_skills=list(mounted_skills),
    )


def _get_skill_mount_snapshot(skills_root: Path, extra_dir: str) -> SkillMountSnapshot:
    key = (str(skills_root), str(Path(extra_dir)) if extra_dir else "")
    with _SKILL_MOUNT_CACHE_LOCK:
        snapshot = _SKILL_MOUNT_CACHE.get(key)
        if snapshot is None:
            snapshot = _build_skill_mount_snapshot(skills_root, extra_dir)
            _SKILL_MOUNT_CACHE[key] = snapshot
        return snapshot


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


def _build_agent_backend_factory(
    *,
    user_id: int,
    workspace: str,
    skills_root: Path,
    extra_dir: str,
    seed_files: dict[str, Any] | None = None,
) -> Callable[[Any], ManagedCompositeBackend]:
    routes: dict[str, Any] = {}

    if skills_root.is_dir():
        routes["/skills/aelin/"] = FilesystemBackend(
            root_dir=skills_root,
            virtual_mode=True,
        )

    extra_root = Path(extra_dir) if extra_dir else None
    if extra_root is not None and extra_root.is_dir():
        routes["/skills/external/"] = FilesystemBackend(
            root_dir=extra_root,
            virtual_mode=True,
        )

    write_file_max_chars = int(getattr(settings, "deepagents_write_file_max_chars", 50000) or 50000)

    def _factory(runtime: Any) -> ManagedCompositeBackend:
        return ManagedCompositeBackend(
            default=StateBackend(runtime),
            routes=dict(routes),
            write_file_max_chars=write_file_max_chars,
            user_id=user_id,
            workspace=workspace,
            seed_files=dict(seed_files or {}),
        )

    return _factory


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


def _read_tool_retry_attempts() -> int:
    try:
        return max(0, int(getattr(settings, "deepagents_read_tool_retry_attempts", 2) or 0))
    except Exception:
        return 0


def _read_tool_retry_backoff_seconds() -> float:
    try:
        return max(0.0, float(getattr(settings, "deepagents_read_tool_retry_backoff_seconds", 0.25) or 0.0))
    except Exception:
        return 0.0


def _tool_retry_delay_seconds(*, attempt_number: int) -> float:
    return _read_tool_retry_backoff_seconds() * max(1, int(attempt_number))


def _is_retryable_tool_error(error: str) -> bool:
    normalized = " ".join(str(error or "").strip().lower().split())
    if not normalized:
        return False
    non_retryable_fragments = (
        "unsupported",
        "invalid ",
        "invalid_",
        "missing ",
        "missing_",
        "authorization required",
        "authorization failed",
        "write failed",
        "write_tools_disabled",
        "call_limit",
        "duplicate_",
        "no new information",
        "no useful",
        "no matching",
        "missing attachment_ids",
        "not available in this run",
        "gws_not_installed",
        "session_factory unavailable",
        "cancelled",
        "busy",
    )
    if any(fragment in normalized for fragment in non_retryable_fragments):
        return False
    retryable_fragments = (
        "timeout",
        "timed out",
        "temporarily unavailable",
        "rate limit",
        "too many requests",
        "connection",
        "connecterror",
        "readerror",
        "transport",
        "proxy",
        "server error",
        "502",
        "503",
        "504",
        "_failed:",
    )
    return any(fragment in normalized for fragment in retryable_fragments)


def _should_retry_tool_result(
    *,
    name: str,
    decision: Any,
    result: dict[str, Any],
) -> bool:
    _ = name
    if bool(getattr(decision, "is_write", False)):
        return False
    if bool(result.get("ok")):
        return False
    if bool(result.get("stop_retry")) or bool(result.get("maybe_applied")):
        return False
    return _is_retryable_tool_error(str(result.get("error") or ""))


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

    usage.note_invocation(name, args)
    tool_key = f"{name}:{call_index}"
    timeout_seconds = max(
        1.0,
        float(getattr(settings, "deepagents_tool_timeout_seconds", 25.0) or 25.0),
    )
    wait_slice_seconds = 0.5
    max_attempts = 1 if decision.is_write else max(1, 1 + _read_tool_retry_attempts())
    attempt_count = 0
    result: dict[str, Any] = _result_error(f"{name}_failed:unknown")

    def _run_once() -> dict[str, Any]:
        slot = _acquire_tool_executor_slot()
        if slot is None:
            busy_result = {
                "ok": False,
                "error": (
                    f"{name}_busy: previous long-running tool calls are still draining; "
                    "stop using tools for now and answer from current evidence"
                ),
                "stop_retry": True,
            }
            if decision.is_write:
                busy_result["maybe_applied"] = True
            return busy_result

        executor, semaphore = slot
        future = _submit_tool_future(executor, semaphore, handler, context, args)
        cancelled_midflight = False
        deadline = perf_counter() + timeout_seconds

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
            cancelled_result = _result_error(
                f"{name}_cancelled: request cancelled while tool was running"
            )
            cancelled_result["stop_retry"] = True
            if decision.is_write:
                cancelled_result["maybe_applied"] = True
                cancelled_result["error"] = (
                    f"{name}_cancelled: request cancelled while the write tool was running; "
                    "the operation may still complete in the background, so do not retry the same write blindly"
                )
            return cancelled_result

        if not future.done():
            timeout_result = _result_error(
                f"{name}_timeout: tool exceeded {int(timeout_seconds)}s; "
                "stop using this tool in this run and answer from current evidence"
            )
            if decision.is_write:
                timeout_result["stop_retry"] = True
                timeout_result["maybe_applied"] = True
                timeout_result["error"] = (
                    f"{name}_timeout: tool exceeded {int(timeout_seconds)}s; "
                    "the write may still complete in the background, so do not retry the same write blindly"
                )
            return timeout_result

        try:
            raw_result = future.result()
        except BaseException as exc:  # noqa: BLE001
            return _result_error(f"{name}_failed:{str(exc)[:160]}")
        if isinstance(raw_result, dict):
            return raw_result
        return _result_error(f"{name}_failed:tool returned invalid payload")

    while attempt_count < max_attempts:
        if is_cancelled(cancel_token):
            raise DeepAgentsCancelled("cancelled")
        attempt_count += 1
        result = _run_once()
        if attempt_count >= max_attempts or not _should_retry_tool_result(
            name=name,
            decision=decision,
            result=result,
        ):
            break
        delay_seconds = _tool_retry_delay_seconds(attempt_number=attempt_count)
        _log.warning(
            "deepagents_read_tool_retry name=%s attempt=%s max_attempts=%s delay_seconds=%s error=%s",
            name,
            attempt_count,
            max_attempts,
            round(delay_seconds, 3),
            str(result.get("error") or "")[:160],
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    if attempt_count > 1 and isinstance(result, dict):
        result = {**result, "attempts": attempt_count}

    latency_ms = int((perf_counter() - started) * 1000)
    usage.total_calls += 1
    if decision.is_write:
        usage.write_calls += 1
    usage.note_result(result)
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
    if attempt_count > 1 and summary:
        summary = f"{summary} after {attempt_count} attempts"

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
            "memory_search",
            tool_memory_search,
            MemorySearchToolInput,
            ["query", "top_k", "kinds"],
        ),
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
    if bool(getattr(settings, "desktop_plugin_execute_enabled", False)):
        tools.append(
            _make_structured_tool(
                "execute",
                tool_execute,
                ExecuteToolInput,
                ["command", "cwd", "timeout_ms"],
            )
        )
    return tools, tool_runs, usage


def build_chat_agent(
    *,
    service: LLMService,
    provider: str,
    context: ToolRuntimeContext,
    limiter: ToolCallLimiter,
    memory_text: str,
    query_hint: str = "",
    context_schema: type[Any] | None = None,
    skills_root: Path | None = None,
    cancel_token: Any | None = None,
) -> tuple[Any, ToolPolicyUsage, list[dict[str, Any]], dict[str, Any]]:
    """
    Construct a DeepAgents chat agent along with tool usage trackers and
    dynamic thread files for memory + runtime capabilities.
    """
    chat_model = _build_chat_model(service, provider)
    if chat_model is None:
        return None, ToolPolicyUsage(), [], {}

    tools, tool_runs, usage = build_chat_tools(
        context=context,
        limiter=limiter,
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
        "- memory_search: use it before opening /memory/*.md files when you need long-term memory; prefer a specific query and optional kinds filter.\n"
        "- web_search: always provide a non-empty query; avoid repeated near-duplicate queries; stop once you have enough evidence.\n"
        "- attachment_search: when the user asks about uploaded files, call attachment_search with a concrete non-empty query describing the requested facts. "
        "If this run already scopes uploaded attachments for you, attachment_ids may be omitted and the runtime will apply the scoped ids automatically. "
        "Do not claim an attachment is unavailable unless attachment_search actually failed in this run.\n"
        "- google_workspace: choose a concrete action and include all required fields before calling; never blindly retry writes.\n"
        "- device: only use status/open_url/open_aelin when the user explicitly asks for desktop or browser navigation; open_url requires a valid http(s) URL.\n"
        "- screen_get: capture only when visual evidence is necessary; avoid repeated screenshots with the same arguments.\n"
        "- execute: use only for short, non-interactive local commands; always provide a concrete command; avoid shells, dev servers, or commands that may wait for user input.\n"
        f"{_current_date_context()}\n"
        "If the user asks about date-sensitive facts, keep the answer explicitly grounded to the current date context above.\n"
        "If search results contain stale dates, say that clearly instead of silently treating them as current.\n"
        "Treat /memory/AGENTS.md as the compact runtime memory projection. Use memory_search and the other /memory/*.md files for deeper long-term memory only when needed.\n"
        "Read skills on demand from /skills/... when a matching skill is relevant.\n"
        "Never claim you searched, opened, read, or cited an external source unless the corresponding tool call succeeded in this run.\n"
        "If a required tool or skill is unavailable, say so explicitly instead of implying the action completed."
    )

    skills_root = skills_root or (_backend_root() / "deepagents_skills")
    extra_dir = str(getattr(settings, "deepagents_extra_skills_dir", "") or "").strip()
    build_started = time.perf_counter()
    skill_snapshot = _get_skill_mount_snapshot(skills_root, extra_dir)
    skill_snapshot_ms = int((time.perf_counter() - build_started) * 1000)
    memory_bundle: dict[str, Any] = {}
    memory_service = getattr(context, "memory_service", None)
    if memory_service is not None:
        memory_started = time.perf_counter()
        try:
            memory_bundle = memory_service.get_memory_bundle(
                user_id=int(getattr(context, "user_id", 0) or 0),
                workspace=str(getattr(context, "workspace", "default") or "default"),
                fallback_agents_text=memory_text,
                query_hint=query_hint,
            )
        except Exception:
            memory_bundle = {}
        memory_bundle_ms = int((time.perf_counter() - memory_started) * 1000)
    else:
        memory_bundle_ms = 0
    if not memory_bundle:
        prompt_text = str(memory_text or "").strip()
        memory_bundle = {
            "prompt_path": "/memory/AGENTS.md",
            "prompt_text": prompt_text,
            "files": {"/memory/AGENTS.md": prompt_text} if prompt_text else {},
            "memory_paths": ["/memory/AGENTS.md"] if prompt_text else [],
            "index": {},
        }

    memory_files = {
        str(path): str(text or "").strip()
        for path, text in dict(memory_bundle.get("files") or {}).items()
        if str(path or "").strip() and str(text or "").strip()
    }
    memory_paths = [
        str(path)
        for path in list(memory_bundle.get("memory_paths") or [])
        if str(path or "").strip()
    ]

    files: dict[str, Any] = {}
    for path, text in memory_files.items():
        files[path] = create_file_data(text)
    files["/runtime/capabilities.json"] = create_file_data(
        json.dumps(
            {
                "tools": [tool.name for tool in tools],
                "skill_sources": skill_snapshot.skill_sources,
                "mounted_skills": skill_snapshot.mounted_skills,
                "memory_files": sorted(memory_files.keys()),
                "memory_runtime_prompt_path": str(memory_bundle.get("prompt_path") or "/memory/AGENTS.md"),
                "memory_index": dict(memory_bundle.get("index") or {}),
                "available_attachment_ids": list(context.available_attachment_ids or []),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    _log.debug(
        "build_chat_agent_ready user_id=%s workspace=%s skill_snapshot_ms=%s memory_bundle_ms=%s memory_files=%s",
        getattr(context, "user_id", 0),
        getattr(context, "workspace", "default"),
        skill_snapshot_ms,
        memory_bundle_ms,
        len(memory_files),
    )

    backend_factory = _build_agent_backend_factory(
        user_id=int(getattr(context, "user_id", 0) or 0),
        workspace=str(getattr(context, "workspace", "default") or "default"),
        skills_root=skills_root,
        extra_dir=extra_dir,
        seed_files=files,
    )

    agent = create_deep_agent(
        model=chat_model,
        system_prompt=system_prompt,
        backend=backend_factory,
        tools=tools,
        middleware=_build_agent_middleware(),
        skills=skill_snapshot.skill_sources or None,
        memory=memory_paths or None,
        context_schema=context_schema,
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

        build_started = time.perf_counter()
        agent, usage, raw_tool_runs, files_mapping = build_chat_agent(
            service=service,
            provider=provider,
            context=context,
            limiter=limiter,
            memory_text=memory_text,
            query_hint=query,
            cancel_token=cancel_token,
        )
        build_agent_ms = int((time.perf_counter() - build_started) * 1000)
        if agent is None:
            return _loop_result(ok=False, error="llm_not_configured")

        capabilities = _parse_capabilities_file(files_mapping)
        capability_summary = (
            f"tools={len(list(capabilities.get('tools') or []))}; "
            f"skills={len(list(capabilities.get('mounted_skills') or []))}; "
            f"memory_files={len(list(capabilities.get('memory_files') or []))}; "
            f"build_agent_ms={build_agent_ms}"
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
        invoke_started = time.perf_counter()
        response = agent.invoke(invoke_payload)
        invoke_ms = int((time.perf_counter() - invoke_started) * 1000)
        if is_cancelled(cancel_token):
            raise DeepAgentsCancelled("cancelled")
        capability_summary = f"{capability_summary}; invoke_ms={invoke_ms}"
        _log.debug(
            "run_deepagents_loop_completed provider=%s build_agent_ms=%s invoke_ms=%s tools=%s writes=%s",
            provider,
            build_agent_ms,
            invoke_ms,
            getattr(usage, "total_calls", 0),
            getattr(usage, "write_calls", 0),
        )

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

