from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI

from app.services.aelin_loop_types import AelinAgentLoopResult, AgentLoopTraceStep, AgentLoopToolRun
from app.services.aelin_tools import AelinToolHub
from app.services.llm import LLMService
from app.services.aelin_tool_policy import AelinToolPolicy
from app.services.deepagents_graph import build_chat_agent

_log = logging.getLogger(__name__)


def _build_chat_model(service: LLMService, provider: str) -> ChatOpenAI | None:
    """
    根据 Aelin 的 AgentConfig 构造 DeepAgents 使用的底层 ChatModel。

    目前该函数仅由 deepagents_graph.build_chat_agent 复用，用于统一
    ChatModel 的构造逻辑；run_deepagents_loop 自身不再直接依赖它。
    """
    try:
        model_name = getattr(service.config, "model", "") or "gpt-4o-mini"
        temperature = float(getattr(service.config, "temperature", 0.0) or 0.0)

        # service.api_key 与 base_url 由 LLMService 统一管理，沿用原有
        # OpenAI 兼容策略，这样支持 Nvidia / DeepSeek / 自建 proxy 等。
        api_key = getattr(service, "api_key", None)
        base_url_raw = getattr(service.config, "base_url", "") or ""
        base_url = LLMService._normalize_base_url(base_url_raw) if base_url_raw else None

        if not api_key:
            _log.warning("build_chat_model_missing_api_key provider=%s", provider)
            return None

        # 默认使用 ChatOpenAI 与任意 OpenAI-Compatible endpoint 通信。
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


def _map_tool_runs(raw_tool_runs: list[dict[str, Any]]) -> list[AgentLoopToolRun]:
    return [
        AgentLoopToolRun(
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


def _extract_answer(response: Any) -> str:
    """
    Best-effort extraction of the final text answer from a DeepAgents response.
    """
    try:
        if hasattr(response, "content"):
            return str(getattr(response, "content", "") or "")
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            if "answer" in response:
                return str(response.get("answer") or "")
            if "output" in response:
                return str(response.get("output") or "")
            if "messages" in response:
                msgs = response.get("messages") or []
                if isinstance(msgs, list) and msgs:
                    last = msgs[-1]
                    if hasattr(last, "content"):
                        return str(getattr(last, "content", "") or "")
                    if isinstance(last, dict) and "content" in last:
                        return str(last.get("content") or "")
        return str(response)
    except Exception as exc:  # noqa: BLE001
        _log.warning("deepagents_parse_response_failed error=%s", str(exc)[:160])
        return ""


def _loop_result(
    *,
    ok: bool,
    answer: str,
    stop_reason: str,
    total_calls: int,
    write_calls: int,
    tool_runs: list[AgentLoopToolRun],
    trace_steps: list[AgentLoopTraceStep],
    error: str,
    memory_snapshot: str,
) -> AelinAgentLoopResult:
    return AelinAgentLoopResult(
        ok=ok,
        answer=answer,
        stop_reason=stop_reason,
        total_calls=total_calls,
        write_calls=write_calls,
        tool_runs=tool_runs,
        trace_steps=trace_steps,
        actions=[],
        error=error,
        memory_snapshot=memory_snapshot,
    )


def run_deepagents_loop(
    *,
    service: LLMService,
    provider: str,
    tool_hub: AelinToolHub,
    policy: AelinToolPolicy,
    query: str,
    memory_summary: str,
    history_turns: list[dict[str, Any]],
) -> AelinAgentLoopResult:
    """
    Bridge between Aelin core and a DeepAgents-powered agent loop.
    """
    try:
        agent, usage, raw_tool_runs, files_mapping = build_chat_agent(
            service=service,
            provider=provider,
            tool_hub=tool_hub,
            policy=policy,
            memory_summary=memory_summary,
        )
        if agent is None:
            return _loop_result(
                ok=False,
                answer="",
                stop_reason="llm_not_configured",
                total_calls=0,
                write_calls=0,
                tool_runs=[],
                trace_steps=[AgentLoopTraceStep(stage="agent_loop", status="failed", detail="llm_not_configured")],
                error="llm_not_configured",
                memory_snapshot="",
            )

        # 构造 DeepAgents 期望的消息格式：带有历史对话和当前用户 query。
        messages: list[dict[str, Any]] = []
        for turn in history_turns:
            role = str(turn.get("role") or "").strip()
            content = str(turn.get("content") or "").strip()
            if not role or not content:
                continue
            if role not in {"user", "assistant"}:
                continue
            messages.append({"role": role, "content": content})

        # DeepAgents 主入口通过 chat history 驱动，我们把最新 query 作为最后一条 user 消息。
        latest_query = str(query or "").strip()
        if latest_query:
            messages.append({"role": "user", "content": latest_query})

        invoke_payload: dict[str, Any] = {"messages": messages}
        if files_mapping:
            invoke_payload["files"] = files_mapping

        response = agent.invoke(invoke_payload)
        answer = _extract_answer(response)
        tool_runs = _map_tool_runs(raw_tool_runs)
    except Exception as exc:  # noqa: BLE001
        _log.exception("deepagents_unhandled_error provider=%s", provider)
        return _loop_result(
            ok=False,
            answer="",
            stop_reason="deepagents_unhandled_error",
            total_calls=0,
            write_calls=0,
            tool_runs=[],
            trace_steps=[
                AgentLoopTraceStep(
                    stage="agent_loop",
                    status="failed",
                    detail=f"deepagents_unhandled_error:{str(exc)[:160]}",
                )
            ],
            error=str(exc)[:200],
            memory_snapshot=memory_summary,
        )

    if not answer.strip():
        return _loop_result(
            ok=False,
            answer="",
            stop_reason="empty_answer",
            total_calls=0,
            write_calls=0,
            tool_runs=tool_runs,
            trace_steps=[
                AgentLoopTraceStep(stage="agent_loop", status="failed", detail="empty_answer_from_deepagents"),
            ],
            error="empty_answer_from_deepagents",
            memory_snapshot=memory_summary,
        )

    return _loop_result(
        ok=True,
        answer=answer.strip(),
        stop_reason="completed",
        total_calls=usage.total_calls,
        write_calls=usage.write_calls,
        tool_runs=tool_runs,
        trace_steps=[
            AgentLoopTraceStep(stage="agent_loop", status="completed", detail="deepagents_core_v0"),
        ],
        error="",
        memory_snapshot=memory_summary,
    )
