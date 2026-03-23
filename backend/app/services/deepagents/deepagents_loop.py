from __future__ import annotations

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI

from app.services.aelin.loop_types import AelinAgentLoopResult, AgentLoopTraceStep, AgentLoopToolRun
from app.services.aelin.tool_hub import AelinToolHub
from app.services.foundation.llm import LLMService
from app.services.aelin.tool_policy import AelinToolPolicy
from app.services.deepagents.deepagents_graph import DeepAgentsCancelled, build_chat_agent

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


def _is_cancelled(cancel_token: Any | None) -> bool:
    return bool(getattr(cancel_token, "cancelled", False))


def _assert_not_cancelled(cancel_token: Any | None) -> None:
    if _is_cancelled(cancel_token):
        raise DeepAgentsCancelled("cancelled")


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


def _has_successful_tool(tool_runs: list[AgentLoopToolRun], name: str, *, actions: set[str] | None = None) -> bool:
    for run in tool_runs:
        if run.name != name or run.status != "completed":
            continue
        if not actions:
            return True
        action = str((run.args or {}).get("action") or "").strip().lower()
        if action in actions:
            return True
    return False


def _answer_has_unsupported_action_claims(answer: str, tool_runs: list[AgentLoopToolRun]) -> str:
    text = str(answer or "").lower()
    if not text:
        return ""

    if any(
        token in text
        for token in (
            "已为你打开",
            "为你打开了",
            "我已打开",
            "已经打开",
            "i opened",
            "opened for you",
        )
    ):
        if not _has_successful_tool(tool_runs, "device", actions={"open_url", "open_aelin"}):
            return "claims_opened_without_device_success"

    if any(
        token in text
        for token in (
            "根据搜索结果",
            "我搜索了",
            "我查了",
            "我查到",
            "i searched",
            "search results",
        )
    ):
        if not _has_successful_tool(tool_runs, "web_search"):
            return "claims_search_without_web_search_success"

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
    images: list[dict[str, Any]] | None = None,
    cancel_token: Any | None = None,
) -> AelinAgentLoopResult:
    """
    Bridge between Aelin core and a DeepAgents-powered agent loop.
    """
    try:
        _assert_not_cancelled(cancel_token)
        agent, usage, raw_tool_runs, files_mapping = build_chat_agent(
            service=service,
            provider=provider,
            tool_hub=tool_hub,
            policy=policy,
            memory_summary=memory_summary,
            cancel_token=cancel_token,
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
        capabilities = _parse_capabilities_file(files_mapping)
        capability_detail = (
            f"tools={len(list(capabilities.get('tools') or []))}; "
            f"skills={len(list(capabilities.get('mounted_skills') or []))}; "
            f"memory_files={len(list(capabilities.get('memory_files') or []))}"
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
            if images:
                content_blocks: list[dict[str, Any]] = [{"type": "text", "text": latest_query}]
                for image in list(images or [])[:4]:
                    data_url = str((image or {}).get("data_url") or "").strip()
                    if not data_url:
                        continue
                    content_blocks.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        }
                    )
                messages.append(
                    {
                        "role": "user",
                        "content": content_blocks if len(content_blocks) > 1 else latest_query,
                    }
                )
            else:
                messages.append({"role": "user", "content": latest_query})

        invoke_payload: dict[str, Any] = {"messages": messages}
        if files_mapping:
            invoke_payload["files"] = files_mapping

        _assert_not_cancelled(cancel_token)
        response = agent.invoke(invoke_payload)
        _assert_not_cancelled(cancel_token)
        answer = _extract_answer(response)
        tool_runs = _map_tool_runs(raw_tool_runs)
        unsupported_claim = _answer_has_unsupported_action_claims(answer, tool_runs)
        trace_steps = [
            AgentLoopTraceStep(stage="runtime.capabilities", status="completed", detail=capability_detail),
        ]
        if unsupported_claim:
            return _loop_result(
                ok=False,
                answer="",
                stop_reason=unsupported_claim,
                total_calls=usage.total_calls,
                write_calls=usage.write_calls,
                tool_runs=tool_runs,
                trace_steps=[
                    *trace_steps,
                    AgentLoopTraceStep(stage="agent_loop", status="failed", detail=unsupported_claim),
                ],
                error=unsupported_claim,
                memory_snapshot=memory_summary,
            )
    except DeepAgentsCancelled:
        return _loop_result(
            ok=False,
            answer="",
            stop_reason="cancelled",
            total_calls=0,
            write_calls=0,
            tool_runs=[],
            trace_steps=[
                AgentLoopTraceStep(
                    stage="agent_loop",
                    status="cancelled",
                    detail="cancelled",
                )
            ],
            error="cancelled",
            memory_snapshot=memory_summary,
        )
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
                AgentLoopTraceStep(stage="runtime.capabilities", status="completed", detail=capability_detail),
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
            AgentLoopTraceStep(stage="runtime.capabilities", status="completed", detail=capability_detail),
            AgentLoopTraceStep(stage="agent_loop", status="completed", detail="deepagents_core_v0"),
        ],
        error="",
        memory_snapshot=memory_summary,
    )

