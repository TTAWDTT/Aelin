from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models import User
from app.schemas import (
    AelinAction,
    AelinChatRequest,
    AelinChatResponse,
    AelinToolStep,
)
from app.services.aelin_tools import AelinToolHub
from app.services.deepagents_loop import run_deepagents_loop
from app.services.aelin_tool_policy import AelinToolPolicy
from app.services.aelin_chat_dispatch import dispatch_aelin_chat as _dispatch_aelin_chat_service
from app.services.aelin_utils import normalize_positive_ints
from app.services.tools_files import tool_attachment_search
from app.services.aelin_runtime import (
    normalize_workspace as _normalize_workspace,
    resolve_llm_service as _resolve_llm_service,
)
# Legacy answer-shaping helpers from `aelin_chat_answering` were removed as
# part of the DeepAgents refactor. We intentionally avoid importing them
# here to keep behaviour aligned with the underlying agent graph and to
# reduce hard-coded post-processing.
from app.services.file_memory_bridge import file_memory_bridge
from app.settings import settings
from app.services.aelin_core_support import (
    _scoped_web_search_service,
    _build_context_bundle as _build_context_bundle_inner,
    _build_cached_base_context_bundle as _build_cached_base_context_bundle_inner,
    _empty_memory_snapshot,
    _get_memory_summary_for_chat,
    _file_memory,
)
from app.routers.aelin_text_helpers import (
    _now_ms,
    _pick_expression,
)
router = APIRouter(prefix="/aelin", tags=["aelin"])
_log = logging.getLogger(__name__)

_file_memory = file_memory_bridge

# Keep image Data URL size checks consistent across chat input normalization
# and agent-loop message construction. This mirrors the default from the
# former `aelin_limits` module.
MAX_IMAGE_DATA_URL_LENGTH = 3_000_000

_base_context_cache_lock = threading.Lock()
_base_context_cache: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}


def _build_context_bundle(
    db: Session,
    user_id: int,
    *,
    workspace: str,
    query: str,
) -> dict[str, Any]:
    """Thin forwarder to the shared context-bundle service helper."""
    return _build_context_bundle_inner(db, user_id, workspace=workspace, query=query)


def _build_cached_base_context_bundle(
    db: Session,
    user_id: int,
    *,
    workspace: str,
) -> dict[str, Any]:
    """Thin forwarder to the cached base context helper."""
    return _build_cached_base_context_bundle_inner(db, user_id, workspace=workspace)

def _normalize_images(raw_images: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw_images[:4]:
        data_url = str(getattr(item, "data_url", "") or "").strip()
        name = str(getattr(item, "name", "") or "").strip()[:120]
        if not data_url.startswith("data:image/"):
            continue
        if ";base64," not in data_url:
            continue
        if len(data_url) > MAX_IMAGE_DATA_URL_LENGTH:
            continue
        out.append({"data_url": data_url, "name": name})
    return out


def _normalize_history(raw_turns: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw_turns[-12:]:
        role = str(getattr(item, "role", "") or "").strip().lower()
        content = str(getattr(item, "content", "") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        if not content:
            continue
        out.append({"role": role, "content": content[:3000]})
    return out


def _normalize_attachment_ids(raw_ids: list[Any]) -> list[int]:
    return normalize_positive_ints(raw_ids, cap=20)


def _build_attachment_prefetch_fallback_response(
    *,
    payload: AelinChatRequest,
    memory_summary: str,
    prefetch_result: dict[str, Any],
    reason: str,
    prefixed_traces: list[AelinToolStep] | None = None,
) -> AelinChatResponse | None:
    if not bool(prefetch_result.get("ok")):
        return None
    hits = prefetch_result.get("hits")
    if not isinstance(hits, list) or not hits:
        return None

    lines: list[str] = []
    for idx, hit in enumerate(hits[:5], start=1):
        if not isinstance(hit, dict):
            continue
        text = " ".join(str(hit.get("text") or "").strip().split())
        if not text:
            continue
        citation = hit.get("citation")
        citation_map = citation if isinstance(citation, dict) else {}
        file_name = str(citation_map.get("file_name") or "附件").strip() or "附件"
        loc_parts: list[str] = []
        if citation_map.get("page"):
            loc_parts.append(f"第{int(citation_map.get('page') or 0)}页")
        if citation_map.get("slide"):
            loc_parts.append(f"第{int(citation_map.get('slide') or 0)}页幻灯片")
        if citation_map.get("sheet"):
            loc_parts.append(f"Sheet={str(citation_map.get('sheet') or '')[:40]}")
        if citation_map.get("row_range"):
            loc_parts.append(f"行={str(citation_map.get('row_range') or '')[:40]}")
        loc_text = f"（{'，'.join(loc_parts)}）" if loc_parts else ""
        lines.append(f"{idx}. {file_name}{loc_text}: {text[:220]}")

    if not lines:
        return None

    if reason == "llm_unavailable":
        head = "当前模型不可用，我先基于已解析附件给你返回可用片段："
    else:
        head = "本轮 Agent Loop 未稳定产出，我先基于已解析附件给你返回可用片段："
    answer = f"{head}\n\n" + "\n".join(lines)
    trace_steps: list[AelinToolStep] = [*(prefixed_traces or [])]
    trace_steps.append(
        AelinToolStep(
            stage="agent_loop",
            status="completed",
            detail=f"attachment_fallback:{reason}; hits={len(lines)}",
            count=len(lines),
            ts=_now_ms(),
        )
    )
    return AelinChatResponse(
        answer=answer,
        expression=_pick_expression(payload.query, answer),
        citations=[],
        actions=[],
        tool_trace=trace_steps[:64],
        memory_summary=memory_summary,
        generated_at=datetime.now(timezone.utc),
    )


def _try_agent_loop_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    persist_memory: bool = True,
    force_disable_writes: bool = False,
    cancel_token: Any | None = None,
) -> AelinChatResponse | None:
    pre_loop_started = time.perf_counter()
    query_preview = " ".join(str(payload.query or "").split())[:120]
    prefixed_traces: list[AelinToolStep] = []
    prefixed_actions: list[AelinAction] = []
    attachment_prefetch_result: dict[str, Any] = {}

    def _emit_prefixed(stage: str, *, status: str, detail: str = "", count: int = 0) -> None:
        step = AelinToolStep(
            stage=str(stage or "agent_loop")[:80],
            status=str(status or "completed")[:24],
            detail=str(detail or "")[:240],
            count=max(0, int(count or 0)),
            ts=_now_ms(),
        )
        prefixed_traces.append(step)
        if event_cb is not None:
            try:
                event_cb("trace", {"step": step.model_dump()})
            except Exception:
                pass

    resolve_started = time.perf_counter()
    service, provider = _resolve_llm_service(db, current_user)
    resolve_latency_ms = int((time.perf_counter() - resolve_started) * 1000)
    _log.info(
        "agent_loop preflight phase=resolve_service user_id=%s source=%s workspace=%s provider=%s latency_ms=%s query=%s",
        int(current_user.id),
        str(getattr(payload, "source", "chat_ui") or "chat_ui")[:32],
        _normalize_workspace(payload.workspace),
        str(provider or ""),
        resolve_latency_ms,
        query_preview,
    )
    _emit_prefixed("preflight.resolve_service", status="completed", detail=f"provider={provider}; latency_ms={resolve_latency_ms}", count=1)
    llm_available = not (provider == "rule_based" or not service.is_configured())

    workspace = _normalize_workspace(payload.workspace)
    summary_started = time.perf_counter()
    memory_summary = _get_memory_summary_for_chat(db, current_user.id, workspace=workspace)
    summary_latency_ms = int((time.perf_counter() - summary_started) * 1000)
    _log.info(
        "agent_loop preflight phase=memory_summary user_id=%s source=%s workspace=%s latency_ms=%s",
        int(current_user.id),
        str(getattr(payload, "source", "chat_ui") or "chat_ui")[:32],
        workspace,
        summary_latency_ms,
    )
    _emit_prefixed(
        "preflight.memory_summary",
        status="completed",
        detail=f"latency_ms={summary_latency_ms}",
        count=1,
    )

    attachment_ids = _normalize_attachment_ids(getattr(payload, "attachment_ids", []))

    history_turns: list[dict[str, str]] = []
    images: list[dict[str, str]] = []
    if llm_available:
        normalize_started = time.perf_counter()
        history_turns = _normalize_history(payload.history)
        images = _normalize_images(payload.images)
        normalize_latency_ms = int((time.perf_counter() - normalize_started) * 1000)
        _log.info(
            "agent_loop preflight phase=normalize_inputs user_id=%s source=%s workspace=%s history_turns=%s images=%s latency_ms=%s",
            int(current_user.id),
            str(getattr(payload, "source", "chat_ui") or "chat_ui")[:32],
            workspace,
            len(history_turns),
            len(images),
            normalize_latency_ms,
        )
        _emit_prefixed(
            "preflight.normalize_inputs",
            status="completed",
            detail=f"history_turns={len(history_turns)}; images={len(images)}; latency_ms={normalize_latency_ms}",
            count=len(history_turns) + len(images),
        )
    elif not attachment_ids:
        return None

    tool_hub_started = time.perf_counter()
    tool_hub = AelinToolHub(
        db=db,
        user_id=current_user.id,
        workspace=workspace,
        web_search_service=_scoped_web_search_service(getattr(service.config, "web_search_proxy_url", "")),
        available_attachment_ids=attachment_ids,
        llm_service=service,
    )
    tool_hub_latency_ms = int((time.perf_counter() - tool_hub_started) * 1000)
    _log.info(
        "agent_loop preflight phase=tool_hub_ready user_id=%s source=%s workspace=%s latency_ms=%s",
        int(current_user.id),
        str(getattr(payload, "source", "chat_ui") or "chat_ui")[:32],
        workspace,
        tool_hub_latency_ms,
    )
    _emit_prefixed("preflight.tool_hub_ready", status="completed", detail=f"latency_ms={tool_hub_latency_ms}", count=1)

    def _ensure_attachment_prefetch() -> dict[str, Any]:
        nonlocal attachment_prefetch_result
        if attachment_prefetch_result:
            return attachment_prefetch_result
        if not attachment_ids:
            attachment_prefetch_result = {"ok": False, "error": "missing_attachment_ids"}
            return attachment_prefetch_result
        attachment_prefetch_args = {
            "query": str(payload.query or "请总结附件主要内容")[:500],
            "attachment_ids": attachment_ids[:20],
            "top_k": 10,
            "mode": "hybrid",
        }
        prefetch_started = time.perf_counter()
        attachment_prefetch_result = tool_attachment_search(tool_hub, attachment_prefetch_args)
        prefetch_latency_ms = int((time.perf_counter() - prefetch_started) * 1000)
        if bool(attachment_prefetch_result.get("ok")):
            _emit_prefixed(
                "attachment_prefetch",
                status="completed",
                detail=f"hits={int(attachment_prefetch_result.get('total') or 0)}; latency_ms={prefetch_latency_ms}",
                count=int(attachment_prefetch_result.get("total") or 0),
            )
        else:
            _emit_prefixed(
                "attachment_prefetch",
                status="failed",
                detail=f"{str(attachment_prefetch_result.get('error') or 'unknown')[:140]}; latency_ms={prefetch_latency_ms}",
                count=0,
            )
        return attachment_prefetch_result

    if not llm_available:
        _ensure_attachment_prefetch()
        fallback_resp = _build_attachment_prefetch_fallback_response(
            payload=payload,
            memory_summary=memory_summary,
            prefetch_result=attachment_prefetch_result,
            reason="llm_unavailable",
            prefixed_traces=prefixed_traces,
        )
        if fallback_resp is not None:
            return fallback_resp
        return None

    allow_write_tools = bool(getattr(settings, "aelin_agent_loop_allow_write_tools", False))

    policy = AelinToolPolicy(
        max_tool_calls=int(getattr(settings, "aelin_agent_loop_max_tool_calls", 512) or 512),
        max_write_calls=int(getattr(settings, "aelin_agent_loop_max_write_calls", 128) or 128),
        allow_write_tools=(False if force_disable_writes else allow_write_tools),
    )
    _log.info(
        "agent_loop preflight phase=runner_ready user_id=%s source=%s workspace=%s total_preflight_ms=%s",
        int(current_user.id),
        str(getattr(payload, "source", "chat_ui") or "chat_ui")[:32],
        workspace,
        int((time.perf_counter() - pre_loop_started) * 1000),
    )
    _emit_prefixed(
        "preflight.runner_ready",
        status="completed",
        detail=f"total_preflight_ms={int((time.perf_counter() - pre_loop_started) * 1000)}",
        count=1,
    )

    result = run_deepagents_loop(
        service=service,
        provider=provider,
        tool_hub=tool_hub,
        policy=policy,
        query=payload.query,
        memory_summary=memory_summary,
        history_turns=history_turns,
    )

    trace_steps: list[AelinToolStep] = [*prefixed_traces]
    latest_memory_snapshot = str(getattr(result, "memory_snapshot", "") or "")

    def _emit_trace(step: AelinToolStep) -> None:
        trace_steps.append(step)
        if event_cb is not None:
            try:
                event_cb("trace", {"step": step.model_dump()})
            except Exception:
                pass

    # 先映射 DeepAgents 提供的高层 trace 步骤。
    for step in result.trace_steps:
        trace = AelinToolStep(
            stage=str(step.stage or "agent_loop")[:80],
            status=str(step.status or "completed")[:24],
            detail=str(step.detail or "")[:240],
            count=max(0, int(step.count or 0)),
            ts=max(0, int(step.ts or _now_ms())),
        )
        _emit_trace(trace)

    for run in result.tool_runs:
        if run.name == "web_search" and isinstance(run.error, str) and run.error.startswith("missing query"):
            continue

        detail = run.error or ""
        if not detail:
            # 对成功调用给一个简洁摘要，避免塞入整个 result。
            scope = ""
            try:
                scope = str(run.result.get("scope") or "")
            except Exception:
                scope = ""
            detail = f"{run.name}({len(run.args)} args) -> {scope}".strip()

        stage = "agent_loop_tool"

        tool_trace = AelinToolStep(
            stage=stage,
            status=str(run.status or "completed")[:24],
            detail=detail[:240],
            count=1,
            ts=_now_ms(),
        )
        _emit_trace(tool_trace)

    if not bool(result.ok) or not str(result.answer or "").strip():
        _ensure_attachment_prefetch()
        fallback_resp = _build_attachment_prefetch_fallback_response(
            payload=payload,
            memory_summary=memory_summary,
            prefetch_result=attachment_prefetch_result,
            reason="agent_loop_no_result",
            prefixed_traces=trace_steps,
        )
        if fallback_resp is not None:
            return fallback_resp
        if event_cb is not None:
            try:
                event_cb(
                    "trace",
                    {
                        "step": AelinToolStep(
                            stage="agent_loop",
                            status="failed",
                            detail=f"fallback_to_legacy:{str(result.stop_reason or 'unknown')[:120]}",
                            count=0,
                            ts=_now_ms(),
                        ).model_dump()
                    },
                )
            except Exception:
                pass
        return None

    if persist_memory and payload.use_memory:
        # Persist DeepAgents-style AGENTS.md snapshot for this workspace so that
        # future runs can treat it as canonical long-term memory.
        try:
            snapshot = latest_memory_snapshot or memory_summary
            if snapshot.strip():
                _file_memory.write_agents_memory(
                    user_id=int(current_user.id),
                    workspace=workspace,
                    content=snapshot,
                )
        except Exception:
            # Persistence failures should not break the main chat flow.
            pass

    expression = _pick_expression(payload.query, result.answer)
    actions: list[AelinAction] = [*prefixed_actions]
    for raw in result.actions[:4]:
        kind = str(raw.get("kind") or "").strip()
        title = str(raw.get("title") or "").strip()
        detail = str(raw.get("detail") or "").strip()
        if not kind or not title:
            continue
        payload_map = {
            str(k): str(v)
            for k, v in raw.items()
            if str(k) not in {"kind", "title", "detail"} and str(v or "").strip()
        }
        actions.append(AelinAction(kind=kind[:32], title=title[:120], detail=detail[:220], payload=payload_map))

    return AelinChatResponse(
        answer=str(result.answer or "").strip(),
        expression=expression,
        citations=[],
        actions=actions,
        tool_trace=trace_steps[:64],
        memory_summary=memory_summary,
        generated_at=datetime.now(timezone.utc),
    )


def _aelin_chat_impl(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
) -> AelinChatResponse:
    """
    Legacy retrieval-era chat implementation (removed).

    DeepAgents agent loop is now the only supported chat path. This stub is
    preserved solely so that older tests and imports that reference
    `_aelin_chat_impl` do not crash at import time. Any direct call into this
    function is considered a bug.
    """
    _ = (payload, db, current_user, event_cb)
    raise RuntimeError(
        "legacy _aelin_chat_impl is no longer supported; use agent loop only"
    )


def _dispatch_aelin_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> AelinChatResponse:
    """
    Public chat entry used by routers and worker threads.

    This is a thin wrapper around the DeepAgents-based agent loop; if the
    loop fails to produce a usable answer, it returns a standardized fallback
    response via `dispatch_aelin_chat`.
    """
    return _dispatch_aelin_chat_service(
        payload,
        db,
        current_user,
        event_cb=event_cb,
        cancel_token=cancel_token,
        try_agent_loop_chat=_try_agent_loop_chat,
        pick_expression=_pick_expression,
        now_ms=_now_ms,
    )
