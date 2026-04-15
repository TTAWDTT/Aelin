from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from langgraph_sdk.runtime import ServerRuntime

from agent_server import agent_factory, graph_cache, runtime_context
from app.db import create_session
from app.services.deepagents.environment_contract import validate_deepagents_environment
from app.services.deepagents.deepagents_graph import build_chat_agent
from app.services.deepagents.run_context import DeepAgentsRunContext
from app.services.deepagents.runtime_resolver import (
    build_tool_call_limiter,
    resolve_deepagents_runtime,
)
from app.services.deepagents.tool_runtime import build_tool_runtime_context


_LOG = logging.getLogger(__name__)
_reset_graph_agent_cache_for_tests = graph_cache.reset_graph_agent_cache_for_tests
validate_deepagents_environment()


def _get_placeholder_agent() -> Any:
    return graph_cache.get_placeholder_agent(_build_placeholder_agent)


def _build_placeholder_agent() -> Any:
    return agent_factory.build_placeholder_agent(
        build_chat_agent=build_chat_agent,
        build_tool_runtime_context=build_tool_runtime_context,
        build_tool_call_limiter=build_tool_call_limiter,
    )


def _build_runtime_agent(
    user_id: int,
    context: DeepAgentsRunContext | dict[str, Any] | None,
) -> Any:
    return agent_factory.build_runtime_agent(
        user_id=user_id,
        context=context,
        create_session=create_session,
        context_value=runtime_context.context_value,
        resolve_deepagents_runtime=resolve_deepagents_runtime,
        build_chat_agent=build_chat_agent,
        logger=_LOG,
    )


async def _resolve_graph_agent(runtime: ServerRuntime[DeepAgentsRunContext]) -> Any:
    execution_runtime = runtime.execution_runtime
    if execution_runtime is None:
        return await asyncio.to_thread(_get_placeholder_agent)

    context = execution_runtime.context
    user_id = runtime_context.runtime_user_id(runtime, context)
    if user_id <= 0:
        _LOG.warning("agent_server_factory_missing_user_id access_context=%s", runtime.access_context)
        return await asyncio.to_thread(_get_placeholder_agent)

    agent = await asyncio.to_thread(_build_runtime_agent, user_id, context)
    if agent is None:
        _LOG.warning("agent_server_factory_fallback_placeholder user_id=%s", user_id)
        return await asyncio.to_thread(_get_placeholder_agent)
    return agent


@asynccontextmanager
async def make_graph(runtime: ServerRuntime[DeepAgentsRunContext]):
    yield await _resolve_graph_agent(runtime)
