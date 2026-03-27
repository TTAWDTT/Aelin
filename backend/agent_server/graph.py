from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from langgraph_sdk.runtime import ServerRuntime

from app.db import create_session
from app.schemas import AgentConfigOut
from app.services.deepagents.deepagents_graph import build_chat_agent
from app.services.deepagents.run_context import DeepAgentsRunContext
from app.services.deepagents.runtime_resolver import (
    build_tool_call_limiter,
    resolve_deepagents_runtime,
)
from app.services.deepagents.tool_runtime import build_tool_runtime_context
from app.services.foundation.llm import LLMService


_LOG = logging.getLogger(__name__)


def _coerce_positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


def _runtime_user_id(
    runtime: ServerRuntime[DeepAgentsRunContext],
    context: DeepAgentsRunContext | None,
) -> int:
    user = getattr(runtime, "user", None)
    candidates: list[Any] = []
    if user is not None:
        for key in ("user_id", "id"):
            try:
                if key in user:
                    candidates.append(user[key])
            except Exception:
                pass
            candidates.append(getattr(user, key, None))
        candidates.append(getattr(user, "identity", None))
    if context is not None:
        candidates.append(getattr(context, "user_id", None))
    for value in candidates:
        user_id = _coerce_positive_int(value)
        if user_id > 0:
            return user_id
    return 0


def _context_value(context: DeepAgentsRunContext | dict[str, Any] | None, key: str, default: Any) -> Any:
    if context is None:
        return default
    if isinstance(context, dict):
        return context.get(key, default)
    try:
        return getattr(context, key)
    except Exception:
        return default


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


def _build_placeholder_agent() -> Any:
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


def _build_runtime_agent(user_id: int, context: DeepAgentsRunContext | None) -> Any:
    db = create_session()
    try:
        workspace = _context_value(context, "workspace", "default")
        raw_attachment_ids = _context_value(context, "attachment_ids", [])
        _LOG.info(
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
        agent, _, _, _ = build_chat_agent(
            service=resolved.service,
            provider=resolved.provider,
            context=resolved.tool_context,
            limiter=resolved.limiter,
            memory_text=resolved.memory_text,
            context_schema=DeepAgentsRunContext,
        )
        return agent
    finally:
        db.close()


@asynccontextmanager
async def make_graph(runtime: ServerRuntime[DeepAgentsRunContext]):
    execution_runtime = runtime.execution_runtime
    context = execution_runtime.context if execution_runtime is not None else None
    if execution_runtime is None:
        yield await asyncio.to_thread(_build_placeholder_agent)
        return

    user_id = _runtime_user_id(runtime, context)
    if user_id <= 0:
        _LOG.warning("agent_server_factory_missing_user_id access_context=%s", runtime.access_context)
        yield await asyncio.to_thread(_build_placeholder_agent)
        return

    agent = await asyncio.to_thread(_build_runtime_agent, user_id, context)
    if agent is None:
        _LOG.warning("agent_server_factory_fallback_placeholder user_id=%s", user_id)
        yield await asyncio.to_thread(_build_placeholder_agent)
        return
    yield agent
