from __future__ import annotations

import json
import hashlib
import logging
import os
import platform
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import crud
from app.db import create_session
from app.db import get_session
from app.models import Contact, Message, User
from app.routers.auth import get_current_user
from app.schemas import (
    AelinAction,
    AelinChatRequest,
    AelinChatResponse,
    AelinCitation,
    AelinLayoutCard,
    AelinMemoryLayerItem,
    AelinMemoryLayers,
    AelinPinRecommendationItem,
    AelinToolStep,
    AelinTodoItem,
    AgentFocusItemOut,
    AgentMemoryNoteOut,
)
from app.services.agent_memory import AgentMemoryService
from app.services import content_tagging
from app.services.aelin_tools import (
    AelinToolHub,
    summarize_tool_results_for_prompt,
)
from app.services.deepagents_loop import run_deepagents_loop
from app.services.aelin_tool_policy import AelinToolPolicy
from app.services.aelin_chat_dispatch import (
    dispatch_aelin_chat as _dispatch_aelin_chat_service,
)
from app.services.aelin_media_pipeline import (
    build_media_ingest_answer as _build_media_ingest_answer,
    media_ingest_service as _media_ingest,
)
from app.services.aelin_limits import MAX_IMAGE_DATA_URL_LENGTH
from app.services.aelin_utils import normalize_positive_ints
from app.services.aelin_runtime import (
    json_from_text as _json_from_text,
    normalize_workspace as _normalize_workspace,
    resolve_llm_service as _resolve_llm_service,
)
from app.services.aelin_chat_planning import (
    _normalize_search_mode,
    _build_intent_contract,
    _build_web_query_pack,
    _build_retry_web_queries,
    _extract_search_subject,
    _decompose_web_context_boundaries,
    _is_time_sensitive_query,
    _is_sports_result_query,
)
from app.services.aelin_chat_answering import (
    _domain_from_url,
    _looks_like_link_dump_answer,
    _looks_like_non_answer,
    _rule_based_chat_answer,
)
from app.services.aelin_chat_memory import (
    _save_parallel_draft_entry,
)
from app.services.memory_draft import ParallelMemoryDraftResult, build_parallel_memory_draft
from app.services.media_ingest import MediaIngestError
from app.services.file_memory_bridge import file_memory_bridge
from app.services.summarizer import RuleBasedSummarizer
from app.services.sync_jobs import enqueue_sync_job
from app.services.web_search import WebSearchResult, WebSearchService
from app.services.aelin_context_service import (
    build_context_bundle as _build_context_bundle_service,
    build_cached_base_context_bundle as _build_cached_base_context_bundle_service,
)
from app.settings import settings
from app.routers.aelin_text_helpers import (
    _AELIN_EXPRESSION_IDS,
    _apply_answer_emoji,
    _dedupe_citations,
    _expression_mapping_prompt,
    _extract_emoji_tag,
    _extract_expression_tag,
    _now_ms,
    _pick_expression,
)
router = APIRouter(prefix="/aelin", tags=["aelin"])
_log = logging.getLogger(__name__)

_memory = AgentMemoryService()
_summarizer = RuleBasedSummarizer()
_web_search = WebSearchService()
_file_memory = file_memory_bridge
_memory_draft_executor = ThreadPoolExecutor(
    max_workers=max(1, min(8, int(getattr(settings, "aelin_parallel_memory_draft_workers", 4) or 4))),
    thread_name_prefix="aelin-memory-draft",
)

_MAX_WEB_SUBAGENTS = 5
_MAX_LOCAL_SUBAGENTS = 5
_MAX_CONTEXT_BOUNDARIES = 10
_WEB_SEARCH_MAX_RESULTS = 15
_WEB_SEARCH_FETCH_TOP_K = 5
_AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS = max(
    0.0,
    float(getattr(settings, "aelin_base_context_cache_ttl_seconds", 4.0) or 4.0),
)
_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES = max(
    0,
    int(getattr(settings, "aelin_base_context_cache_max_entries", 128) or 128),
)

_MEDIA_URL_RE = re.compile(r"https?://[^\s<>()\"']+")
_MEDIA_SUMMARY_HINTS_ZH = (
    "总结",
    "摘要",
    "读",
    "读取",
    "理解",
    "解析",
    "梳理",
    "提炼",
    "看懂",
    "记住",
)
_MEDIA_SUMMARY_HINTS_EN = (
    "summary",
    "summarize",
    "recap",
    "digest",
    "analyze",
    "ingest",
)

_base_context_cache_lock = threading.Lock()
_base_context_cache: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}


def _scoped_web_search_service(proxy_url: str = "") -> WebSearchService:
    return WebSearchService(
        timeout_seconds=float(getattr(_web_search, "timeout_seconds", 10.0) or 10.0),
        max_parallel_providers=int(getattr(_web_search, "max_parallel_providers", 4) or 4),
        max_parallel_fetch=int(getattr(_web_search, "max_parallel_fetch", 4) or 4),
        enable_reader_fallback=bool(getattr(_web_search, "enable_reader_fallback", True)),
        enable_browser_fallback=bool(getattr(_web_search, "enable_browser_fallback", True)),
        proxy_url=str(proxy_url or "").strip(),
    )


def _build_context_bundle(db: Session, user_id: int, *, workspace: str, query: str) -> dict:
    workspace_norm = _normalize_workspace(workspace)
    return _build_context_bundle_service(
        db,
        user_id,
        workspace=workspace_norm,
        query=query,
        memory_service=_memory,
    )


def _build_cached_base_context_bundle(db: Session, user_id: int, *, workspace: str) -> dict[str, Any]:
    workspace_norm = _normalize_workspace(workspace)
    return _build_cached_base_context_bundle_service(
        db,
        user_id=user_id,
        workspace=workspace_norm,
        memory_service=_memory,
        ttl_seconds=_AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS,
        max_entries=_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES,
        cache=_base_context_cache,
        lock=_base_context_cache_lock,
    )


def _empty_memory_snapshot() -> dict[str, Any]:
    return {
        "active_items": [],
        "matched_items": [],
        "active_count": 0,
        "matched_count": 0,
        "matched_file_items": [],
    }


def _build_cached_memory_snapshot(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    include_file_memory: bool,
) -> dict[str, Any]:
    # The old follow-up subsystem is gone; only file-memory retrieval remains.
    return _empty_memory_snapshot()


def _to_citations(raw_focus_items: list[dict], max_items: int) -> list[AelinCitation]:
    items: list[AelinCitation] = []
    for row in raw_focus_items[: max(1, min(20, max_items))]:
        try:
            items.append(
                AelinCitation(
                    message_id=int(row.get("message_id") or 0),
                    source=str(row.get("source") or "unknown"),
                    source_label=str(row.get("source_label") or row.get("source") or "unknown"),
                    sender=str(row.get("sender") or ""),
                    sender_avatar_url=(
                        str(row.get("sender_avatar_url") or "").strip() or None
                    ),
                    title=str(row.get("title") or ""),
                    received_at=str(row.get("received_at") or ""),
                    score=float(row.get("score") or 0.0),
                )
            )
        except Exception:
            continue
    return items


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


def _extract_first_supported_media_url(query: str) -> tuple[str, str] | None:
    text = str(query or "")
    if not text:
        return None
    for match in _MEDIA_URL_RE.finditer(text):
        raw_url = str(match.group(0) or "").strip().rstrip(".,;:!?)")
        if not raw_url:
            continue
        try:
            platform = _media_ingest.detect_platform(raw_url)
        except Exception:
            platform = "unsupported"
        if platform != "unsupported":
            return raw_url, platform
    return None


def _is_media_summary_intent(query: str, media_url: str) -> bool:
    text = str(query or "")
    stripped = text.replace(media_url, " ")
    stripped = _MEDIA_URL_RE.sub(" ", stripped)
    stripped = re.sub(r"[\s`~!@#$%^&*()_\-+=\[\]{};:'\",.<>/?，。！？、（）【】《》\|]+", " ", stripped).strip()
    if not stripped:
        return True

    lowered = stripped.lower()
    if any(token in lowered for token in _MEDIA_SUMMARY_HINTS_EN):
        return True
    if any(token in stripped for token in _MEDIA_SUMMARY_HINTS_ZH):
        return True
    return len(stripped) <= 6


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


def _get_memory_summary_for_chat(db: Session, user_id: int, *, workspace: str = "default") -> str:
    """
    Build the concise memory summary string used by the agent loop.

    This delegates to AgentMemoryService.build_system_memory_prompt so that
    DeepAgents sees the same AGENTS.md-style view of user memory, instead of
    the legacy raw summary field.
    """
    try:
        summary = _memory.build_system_memory_prompt(db, user_id, query="")
    except Exception:
        # In DeepAgents 模式下，记忆完全依赖 `/memory/AGENTS.md` 虚拟文件；
        # 当构建失败时，不再回退到任何 DB 记忆字段，直接返回空串由上层兜底。
        summary = ""
    return str(summary or "").strip()


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

    # Auto-ingest supported media URLs (YouTube/Bilibili/抖音等) before entering
    # the DeepAgents loop, preserving the old “drop a link → get summary”
    # behaviour while keeping the new runtime.
    media_result: Any | None = None
    media_summary_intent = False
    media_hit = _extract_first_supported_media_url(payload.query)
    if media_hit is not None:
        media_url, media_platform = media_hit
        media_summary_intent = _is_media_summary_intent(payload.query, media_url)
        _emit_prefixed(
            "media_ingest",
            status="running",
            detail=f"{media_platform}:{media_url[:90]}",
            count=0,
        )
        try:
            media_result = _media_ingest.ingest(
                user_id=current_user.id,
                workspace=workspace,
                url=media_url,
                service=service,
                provider=provider,
                languages=None,
            )
            _emit_prefixed(
                "media_ingest",
                status="completed",
                detail=(
                    f"{media_result.platform}; "
                    f"source={media_result.source_type}; "
                    f"conf={media_result.confidence:.2f}"
                ),
                count=1,
            )
        except MediaIngestError as exc:
            _emit_prefixed(
                "media_ingest",
                status="failed",
                detail=f"{exc.code}:{exc.message[:140]}",
                count=0,
            )
            media_result = None
        except Exception as exc:  # pragma: no cover - defensive guardrail
            _emit_prefixed(
                "media_ingest",
                status="failed",
                detail=str(exc)[:160],
                count=0,
            )
            media_result = None

        # If the user essentially asked “帮我读/总结这个链接”，直接返回摘要，
        # 不再进入 DeepAgents 回合，以获得更快、更稳定的体验。
        if media_result is not None and media_summary_intent:
            answer = _build_media_ingest_answer(media_result)
            expression = _pick_expression(payload.query, answer)
            # DeepAgents 记忆收拢后不再依赖 DB 记忆更新，这里仅返回媒体摘要。
            return AelinChatResponse(
                answer=answer,
                expression=expression,
                citations=[],
                actions=[],
                tool_trace=prefixed_traces[:64],
                memory_summary=memory_summary,
                generated_at=datetime.now(timezone.utc),
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
        memory_service=_memory,
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
        attachment_prefetch_result = tool_hub.execute("attachment_search", attachment_prefetch_args)
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

    # 如果已经存在一个活跃 plane task，让模型知道可以“续上”它，
    # 而不是每次都重新开始委派。
    allow_write_tools = bool(getattr(settings, "aelin_agent_loop_allow_write_tools", False))

    policy = AelinToolPolicy(
        max_calls_per_round=int(getattr(settings, "aelin_agent_loop_max_calls_per_round", 2) or 2),
        max_tool_calls=int(getattr(settings, "aelin_agent_loop_max_tool_calls", 6) or 6),
        max_write_calls=int(getattr(settings, "aelin_agent_loop_max_write_calls", 1) or 1),
        allow_write_tools=(
            False
            if force_disable_writes
            else allow_write_tools
        ),
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
        images=images,
        attachment_ids=attachment_ids,
        cancel_token=cancel_token,
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


def _dispatch_aelin_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> AelinChatResponse:
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


def _aelin_chat_impl(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
) -> AelinChatResponse:
    """
    Legacy retrieval-era chat implementation.

    This function is intentionally no longer used in the runtime. The
    DeepAgents-based agent loop is now the only chat path. The symbol is
    preserved so that older tests and router monkeypatches can still
    reference it without breaking, but any direct call is considered a bug.
    """
    raise RuntimeError(
        "legacy _aelin_chat_impl is no longer supported; use agent loop only"
    )
