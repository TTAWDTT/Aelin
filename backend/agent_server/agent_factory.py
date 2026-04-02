from __future__ import annotations

import logging
from typing import Any, Callable

from app.schemas import AgentConfigOut
from app.services.deepagents.run_context import DeepAgentsRunContext
from app.services.foundation.llm import LLMService


def _placeholder_service() -> LLMService:
    return LLMService(
        AgentConfigOut(
            provider="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            temperature=0.2,
            verify_ssl=True,
            has_api_key=True,
            web_search_proxy_url="",
        ),
        "placeholder",
    )


def build_placeholder_agent(
    *,
    build_chat_agent: Callable[..., tuple[Any, Any, Any, Any]],
    build_tool_runtime_context: Callable[..., Any],
    build_tool_call_limiter: Callable[..., Any],
) -> Any:
    agent, _, _, _ = build_chat_agent(
        service=_placeholder_service(),
        provider="openai",
        context=build_tool_runtime_context(
            user_id=0,
            workspace="default",
        ),
        limiter=build_tool_call_limiter(allow_write_tools=False),
        memory_text="",
        context_schema=DeepAgentsRunContext,
    )
    return agent


def build_runtime_agent(
    *,
    user_id: int,
    context: DeepAgentsRunContext | dict[str, Any] | None,
    create_session: Callable[[], Any],
    context_value: Callable[[DeepAgentsRunContext | dict[str, Any] | None, str, Any], Any],
    resolve_deepagents_runtime: Callable[..., Any],
    build_chat_agent: Callable[..., tuple[Any, Any, Any, Any]],
    logger: logging.Logger,
) -> Any:
    db = create_session()
    try:
        workspace = context_value(context, "workspace", "default")
        raw_attachment_ids = context_value(context, "attachment_ids", [])
        logger.info(
            "agent_server_runtime_context user_id=%s workspace=%s attachment_ids=%s context_type=%s",
            user_id,
            workspace,
            raw_attachment_ids,
            type(context).__name__ if context is not None else "None",
        )
        resolved = resolve_deepagents_runtime(
            db,
            user_id=user_id,
            workspace=workspace,
            raw_attachment_ids=raw_attachment_ids,
            session_factory=create_session,
        )
        resolved_user_id = int(getattr(resolved, "user_id", 0) or user_id)
        resolved_workspace = str(getattr(resolved, "workspace", workspace) or workspace or "default")
        resolved_attachment_ids = list(getattr(resolved, "attachment_ids", raw_attachment_ids) or [])

        # Do not cache the runtime DeepAgents agent object itself.
        #
        # build_chat_agent() wires tool closures that capture mutable per-run
        # state such as ToolPolicyUsage and the in-memory tool_runs list. Reusing
        # the compiled agent leaks those counters across runs/threads and can make
        # a fresh run start in an already-stalled state.
        agent, _, _, _ = build_chat_agent(
            service=resolved.service,
            provider=resolved.provider,
            context=resolved.tool_context,
            limiter=resolved.limiter,
            memory_text=resolved.memory_text,
            context_schema=DeepAgentsRunContext,
        )
        if agent is None:
            return None
        logger.debug(
            "agent_server_graph_built_fresh user_id=%s workspace=%s attachment_ids=%s",
            resolved_user_id,
            resolved_workspace,
            resolved_attachment_ids,
        )
        return agent
    finally:
        db.close()


_build_placeholder_agent = build_placeholder_agent
_build_runtime_agent = build_runtime_agent
