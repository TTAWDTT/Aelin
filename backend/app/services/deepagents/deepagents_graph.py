from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from langchain_openai import ChatOpenAI

try:
    from deepagents import create_deep_agent
    from deepagents.backends.utils import create_file_data
except Exception:  # pragma: no cover - fallback for test environments without deepagents
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

from app.services.deepagents.assembly import backend_factory as _backend_factory_module
from app.services.deepagents.assembly.backend_factory import _backend_root, build_agent_backend_factory
from app.services.deepagents.assembly.output_mapping import (
    DeepAgentsCancelled,
    DeepAgentsLoopResult,
    build_loop_result,
    map_tool_runs,
    parse_capabilities_file,
)
from app.services.deepagents.assembly.prompt import build_system_prompt
from app.services.deepagents.assembly.skill_mounts import get_skill_mount_snapshot
from app.services.deepagents.assembly import tool_registry as _tool_registry
from app.services.deepagents.delivery_paths import get_delivery_paths
from app.services.deepagents.model_timeout_middleware import (
    DeepAgentsModelRetryMiddleware,
    DeepAgentsModelTimeoutMiddleware,
    DeepAgentsToolAvailabilityMiddleware,
    DeepAgentsToolMessageSanitizerMiddleware,
)
from app.services.deepagents.tool_runtime import (
    ToolCallLimiter,
    ToolPolicyUsage,
    ToolRuntimeContext,
)
from app.services.deepagents.cancel_utils import is_cancelled
from app.services.deepagents.input_mapping import build_chat_messages
from app.services.deepagents.output_utils import extract_answer
from app.services.foundation.llm import LLMService
from app.services.tools.tools_device import tool_device, tool_screen_get
from app.services.tools.tools_files import tool_attachment_search
from app.services.tools.tools_gws import tool_google_workspace
from app.services.tools.tools_execute import tool_execute
from app.services.tools.tools_present_files import tool_present_files
from app.services.tools.tools_memory import tool_memory_search
from app.services.tools.tools_web import tool_web_search
from app.settings import settings


_log = logging.getLogger(__name__)


# Backward-compatible alias kept for existing tests and imports during the
# first structure-refactor phase. The underlying implementation now lives in
# `deepagents.assembly.prompt`.
_build_system_prompt = build_system_prompt


def _build_agent_backend_factory(
    *,
    user_id: int,
    workspace: str,
    skills_root: Path,
    extra_dir: str,
    seed_files: dict[str, Any] | None = None,
):
    # Keep monkeypatch-friendly compatibility during the first refactor phase:
    # tests and callers may patch symbols on this module and expect the backend
    # factory assembly module to pick them up.
    _backend_factory_module.get_delivery_paths = get_delivery_paths
    return _backend_factory_module.build_agent_backend_factory(
        user_id=user_id,
        workspace=workspace,
        skills_root=skills_root,
        extra_dir=extra_dir,
        seed_files=seed_files,
    )


def build_chat_tools(
    *,
    context: ToolRuntimeContext,
    limiter: ToolCallLimiter,
    cancel_token: Any | None = None,
) -> tuple[list[Any], list[dict[str, Any]], ToolPolicyUsage]:
    # Keep monkeypatch-friendly compatibility during the first refactor phase:
    # tests and callers may patch symbols on this module and expect the tool
    # registry to pick them up.
    _tool_registry.tool_web_search = tool_web_search
    _tool_registry.tool_attachment_search = tool_attachment_search
    _tool_registry.tool_memory_search = tool_memory_search
    _tool_registry.tool_google_workspace = tool_google_workspace
    _tool_registry.tool_device = tool_device
    _tool_registry.tool_screen_get = tool_screen_get
    _tool_registry.tool_execute = tool_execute
    _tool_registry.tool_present_files = tool_present_files
    return _tool_registry.build_chat_tools(
        context=context,
        limiter=limiter,
        cancel_token=cancel_token,
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


def _build_agent_middleware(*, preserved_tools: list[Any] | None = None) -> list[Any]:
    middleware: list[Any] = [
        DeepAgentsToolMessageSanitizerMiddleware(),
    ]
    if preserved_tools:
        middleware.append(
            DeepAgentsToolAvailabilityMiddleware(preserved_tools=list(preserved_tools))
        )
    retry_count = int(getattr(settings, "deepagents_model_transient_error_retries", 2) or 0)
    if retry_count > 0:
        middleware.append(
            DeepAgentsModelRetryMiddleware(
                max_retries=retry_count,
                backoff_seconds=float(
                    getattr(settings, "deepagents_model_transient_error_backoff_seconds", 1.0)
                    or 1.0
                ),
            )
        )
    timeout_seconds = float(getattr(settings, "deepagents_run_timeout_seconds", 75.0) or 0.0)
    if timeout_seconds > 0:
        middleware.append(DeepAgentsModelTimeoutMiddleware(timeout_seconds=timeout_seconds))
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
            # OpenAI-compatible providers can emit malformed streaming tool-call
            # deltas (for example, orphaned argument chunks with no function name).
            # Bypass provider streaming specifically when tools are bound so the
            # model call falls back to a single non-streaming completion.
            disable_streaming="tool_calling",
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
    user_id = int(getattr(context, "user_id", 0) or 0)
    workspace = str(getattr(context, "workspace", "default") or "default")
    delivery_paths = get_delivery_paths(workspace=workspace, user_id=user_id)
    preserved_tools = [
        tool
        for tool in tools
        if str(getattr(tool, "name", "") or "").strip() in {
            "execute",
            "present_files",
        }
    ]

    system_prompt = build_system_prompt(
        [tool.name for tool in tools],
        user_id=user_id,
        workspace=workspace,
    )

    skills_root = skills_root or (_backend_root() / "deepagents_skills")
    extra_dir = str(getattr(settings, "deepagents_extra_skills_dir", "") or "").strip()
    skill_snapshot = get_skill_mount_snapshot(skills_root, extra_dir)
    memory_bundle: dict[str, Any] = {}
    memory_service = getattr(context, "memory_service", None)
    if memory_service is not None:
        try:
            memory_bundle = memory_service.get_memory_bundle(
                user_id=user_id,
                workspace=workspace,
                fallback_agents_text=memory_text,
                query_hint=query_hint,
            )
        except Exception:
            memory_bundle = {}
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
                "memory_runtime_prompt_path": str(
                    memory_bundle.get("prompt_path") or "/memory/AGENTS.md"
                ),
                "memory_index": dict(memory_bundle.get("index") or {}),
                "available_attachment_ids": list(context.available_attachment_ids or []),
                "workspace_virtual_path": delivery_paths.workspace_virtual_path,
                "outputs_virtual_path": delivery_paths.outputs_virtual_path,
                "workspace_local_path": delivery_paths.workspace_dir.as_posix(),
                "outputs_local_path": delivery_paths.outputs_dir.as_posix(),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    backend_factory = build_agent_backend_factory(
        user_id=user_id,
        workspace=workspace,
        skills_root=skills_root,
        extra_dir=extra_dir,
        seed_files=files,
    )

    agent = create_deep_agent(
        model=chat_model,
        system_prompt=system_prompt,
        backend=backend_factory,
        tools=tools,
        middleware=_build_agent_middleware(preserved_tools=preserved_tools),
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

        agent, usage, raw_tool_runs, files_mapping = build_chat_agent(
            service=service,
            provider=provider,
            context=context,
            limiter=limiter,
            memory_text=memory_text,
            query_hint=query,
            cancel_token=cancel_token,
        )
        if agent is None:
            return build_loop_result(ok=False, error="llm_not_configured")

        capabilities = parse_capabilities_file(files_mapping)
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
        tool_runs = map_tool_runs(raw_tool_runs)

        if not answer:
            return build_loop_result(
                ok=False,
                tool_runs=tool_runs,
                total_calls=getattr(usage, "total_calls", 0),
                write_calls=getattr(usage, "write_calls", 0),
                error="empty_answer_from_deepagents",
                capability_summary=capability_summary,
            )

        return build_loop_result(
            ok=True,
            answer=answer,
            tool_runs=tool_runs,
            total_calls=getattr(usage, "total_calls", 0),
            write_calls=getattr(usage, "write_calls", 0),
            capability_summary=capability_summary,
        )
    except DeepAgentsCancelled:
        return build_loop_result(ok=False, cancelled=True, error="cancelled")
    except Exception as exc:  # noqa: BLE001
        _log.exception("deepagents_unhandled_error provider=%s", provider)
        return build_loop_result(
            ok=False,
            error=f"deepagents_unhandled_error:{str(exc)[:160]}",
        )
