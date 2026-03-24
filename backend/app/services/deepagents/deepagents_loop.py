from __future__ import annotations

import json
import logging
from typing import Any

from app.services.aelin.loop_types import (
    AelinAgentLoopResult,
    AgentLoopTraceStep,
    AgentLoopToolRun,
    STOP_REASON_CANCELLED,
    STOP_REASON_CLAIMS_OPENED_WITHOUT_DEVICE_SUCCESS,
    STOP_REASON_CLAIMS_SEARCH_WITHOUT_WEB_SEARCH_SUCCESS,
    STOP_REASON_COMPLETED,
    STOP_REASON_DEEPAGENTS_UNHANDLED_ERROR,
    STOP_REASON_EMPTY_ANSWER,
    STOP_REASON_LLM_NOT_CONFIGURED,
)
from app.services.aelin.tool_hub import AelinToolHub
from app.services.aelin.tool_policy import AelinToolPolicy
from app.services.deepagents.deepagents_graph import DeepAgentsCancelled, build_chat_agent
from app.services.deepagents.cancel_utils import is_cancelled

_log = logging.getLogger(__name__)


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


def _assert_not_cancelled(cancel_token: Any | None) -> None:
    if is_cancelled(cancel_token):
        raise DeepAgentsCancelled(STOP_REASON_CANCELLED)


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
            return STOP_REASON_CLAIMS_OPENED_WITHOUT_DEVICE_SUCCESS

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
            return STOP_REASON_CLAIMS_SEARCH_WITHOUT_WEB_SEARCH_SUCCESS

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
                stop_reason=STOP_REASON_LLM_NOT_CONFIGURED,
                total_calls=0,
                write_calls=0,
                tool_runs=[],
                trace_steps=[
                    AgentLoopTraceStep(
                        stage="agent_loop",
                        status="failed",
                        detail=STOP_REASON_LLM_NOT_CONFIGURED,
                    )
                ],
                error=STOP_REASON_LLM_NOT_CONFIGURED,
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
            if role not in {"user", "assistant", "system"}:
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
            stop_reason=STOP_REASON_CANCELLED,
            total_calls=0,
            write_calls=0,
            tool_runs=[],
            trace_steps=[
                AgentLoopTraceStep(stage="agent_loop", status="cancelled", detail=STOP_REASON_CANCELLED)
            ],
            error=STOP_REASON_CANCELLED,
            memory_snapshot=memory_summary,
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception("deepagents_unhandled_error provider=%s", provider)
        return _loop_result(
            ok=False,
            answer="",
            stop_reason=STOP_REASON_DEEPAGENTS_UNHANDLED_ERROR,
            total_calls=0,
            write_calls=0,
            tool_runs=[],
            trace_steps=[
                AgentLoopTraceStep(
                    stage="agent_loop",
                    status="failed",
                    detail=f"{STOP_REASON_DEEPAGENTS_UNHANDLED_ERROR}:{str(exc)[:160]}",
                )
            ],
            error=str(exc)[:200],
            memory_snapshot=memory_summary,
        )

    if not answer.strip():
        return _loop_result(
            ok=False,
            answer="",
            stop_reason=STOP_REASON_EMPTY_ANSWER,
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
        stop_reason=STOP_REASON_COMPLETED,
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

