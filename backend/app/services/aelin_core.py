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
    AelinDailyBrief,
    AelinDailyBriefAction,
    AelinLayoutCard,
    AelinMemoryLayerItem,
    AelinMemoryLayers,
    AelinNotificationItem,
    AelinPinRecommendationItem,
    AelinToolStep,
    AelinTodoItem,
    AgentFocusItemOut,
    AgentMemoryNoteOut,
)
from app.services.agent_memory import AgentMemoryService, serialize_focus_item
from app.services import content_tagging
from app.services.aelin_tools import (
    AelinToolHub,
    run_aelin_structured_tools,
    should_attempt_aelin_tools,
    should_resume_active_plane_for_query,
    summarize_tool_results_for_prompt,
)
from app.services.aelin_planes import get_active_plane_task
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
    _apply_plan_patch,
    _build_intent_contract,
    _build_retry_web_queries,
    _build_trace_context_boundaries,
    _build_web_query_pack,
    _check_evidence_coverage,
    _critic_tool_plan,
    _decompose_web_context_boundaries,
    _extract_search_subject,
    _is_smalltalk_query,
    _is_sports_result_query,
    _is_time_sensitive_query,
    _judge_answer_grounding,
    _main_agent_route,
    _normalize_context_boundaries,
    _normalize_match_text,
    _normalize_search_mode,
    _parse_json_object,
    _plan_tool_usage,
    _safe_float,
    _safe_int,
    _verify_reply_answer,
)
from app.services.aelin_chat_answering import (
    _compose_web_first_answer,
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
from app.services.openviking_bridge import file_memory_bridge
from app.services.summarizer import RuleBasedSummarizer
from app.services.sync_jobs import enqueue_sync_job
from app.services.web_search import WebSearchResult, WebSearchService
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
_PROACTIVE_STATE_SOURCE_PREFIX = "proactive_state"
_PROACTIVE_SEEN_LIMIT = 180
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


def _to_layout_cards(raw_cards: list[dict]) -> list[AelinLayoutCard]:
    out: list[AelinLayoutCard] = []
    for row in raw_cards[:120]:
        try:
            card = AelinLayoutCard(
                contact_id=int(row.get("contact_id") or 0),
                display_name=str(row.get("display_name") or f"contact-{row.get('contact_id') or 'unknown'}"),
                pinned=bool(row.get("pinned")),
                order=max(0, int(row.get("order") or 0)),
                x=max(0.0, float(row.get("x") or 0.0)),
                y=max(0.0, float(row.get("y") or 0.0)),
                width=float(row.get("width") or 312.0),
                height=float(row.get("height") or 316.0),
            )
        except Exception:
            continue
        if card.contact_id <= 0:
            continue
        out.append(card)
    out.sort(key=lambda x: (x.y, x.x, x.order, x.display_name))
    return out[:80]


def _build_fixed_profile_injection(bundle: dict[str, Any], *, max_items: int = 12) -> list[str]:
    if not isinstance(bundle, dict):
        return []

    safe_limit = max(1, min(24, int(max_items or 12)))
    out: list[str] = []
    seen: set[str] = set()

    def _read(item: Any, key: str) -> str:
        if isinstance(item, dict):
            return str(item.get(key) or "").strip()
        return str(getattr(item, key, "") or "").strip()

    def _push(text: str, *, label: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if not cleaned:
            return
        normalized = cleaned.lower()
        if normalized in seen:
            return
        seen.add(normalized)
        out.append(f"- [{label}] {cleaned[:220]}")

    memory_layers = bundle.get("memory_layers")
    preference_rows = list(getattr(memory_layers, "preferences", []) or [])
    fact_rows = list(getattr(memory_layers, "facts", []) or [])

    for row in preference_rows[:10]:
        title = _read(row, "title")
        detail = _read(row, "detail")
        merged = f"{title}: {detail}" if detail else title
        _push(merged, label="preference")
        if len(out) >= safe_limit:
            return out[:safe_limit]

    for row in fact_rows[:10]:
        title = _read(row, "title")
        detail = _read(row, "detail")
        merged = f"{title}: {detail}" if detail else title
        _push(merged, label="fact")
        if len(out) >= safe_limit:
            return out[:safe_limit]

    profile_kinds = {
        "profile",
        "identity",
        "preference",
        "user_profile",
        "user_note",
        "manual_note",
    }
    notes = bundle.get("notes") if isinstance(bundle.get("notes"), list) else []
    for row in notes:
        kind = _read(row, "kind").lower()
        source = _read(row, "source").lower()
        if (kind not in profile_kinds) and (not source.startswith("profile")):
            continue
        content = _read(row, "content")
        _push(content, label="note")
        if len(out) >= safe_limit:
            break
    return out[:safe_limit]


def _build_context_bundle(db: Session, user_id: int, *, workspace: str, query: str) -> dict:
    workspace_norm = _normalize_workspace(workspace)
    summary = _memory.get_summary(db, user_id)
    note_rows = _memory.list_notes(db, user_id, limit=24)
    focus_items = _memory.build_focus_items(db, user_id, query=query, limit=8)
    notes: list[AgentMemoryNoteOut] = []
    for row in note_rows:
        src = (row.source or "").strip().lower()
        if src == "todo" or src.startswith("card_layout"):
            continue
        notes.append(
            AgentMemoryNoteOut(
                id=row.id,
                kind=row.kind,
                content=row.content,
                source=row.source,
                updated_at=row.updated_at.isoformat() if row.updated_at else "",
            )
        )
        if len(notes) >= 12:
            break

    todos_raw = _memory.list_todos(db, user_id, include_done=False, limit=10)
    todos: list[AelinTodoItem] = []
    for row in todos_raw:
        try:
            todos.append(AelinTodoItem(**row))
        except Exception:
            continue

    pins_raw = _memory.recommend_pins(db, user_id, limit=6)
    pin_recommendations: list[AelinPinRecommendationItem] = []
    for row in pins_raw:
        try:
            pin_recommendations.append(AelinPinRecommendationItem(**row))
        except Exception:
            continue

    layout_rows = _memory.get_latest_layout_cards(db, user_id, workspace=workspace_norm)
    brief_raw = _memory.build_daily_brief_from_items(
        db,
        user_id,
        focus_items=focus_items[:6],
        todos=todos_raw,
    )
    daily_brief = AelinDailyBrief(
        generated_at=brief_raw["generated_at"],
        summary=str(brief_raw.get("summary") or ""),
        top_updates=[AgentFocusItemOut(**item) for item in brief_raw.get("top_updates", [])],
        actions=[AelinDailyBriefAction(**item) for item in brief_raw.get("actions", [])],
    )

    layout_cards = _to_layout_cards(layout_rows)
    memory_layers_raw = _memory.build_memory_layers_from_items(
        summary=summary,
        notes=note_rows,
        focus_items=focus_items,
        todos=todos_raw,
        layout_cards=layout_rows,
        workspace=workspace_norm,
        query=query,
    )
    memory_layers = AelinMemoryLayers(
        facts=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("facts") or [])],
        preferences=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("preferences") or [])],
        in_progress=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("in_progress") or [])],
        generated_at=datetime.now(timezone.utc),
    )
    notifications = [
        AelinNotificationItem(**item)
        for item in _memory.build_notifications_from_items(
            db,
            user_id,
            brief=brief_raw,
            todos=todos_raw,
            limit=24,
        )
    ]

    serialized_focus_items = [serialize_focus_item(item) for item in focus_items]

    return {
        "workspace": workspace_norm,
        "summary": str(summary or ""),
        "focus_items": [AgentFocusItemOut(**item) for item in serialized_focus_items],
        "focus_items_raw": serialized_focus_items,
        "notes": notes,
        "notes_count": len(notes),
        "todos": todos,
        "pin_recommendations": pin_recommendations,
        "daily_brief": daily_brief,
        "layout_cards": layout_cards,
        "memory_layers": memory_layers,
        "notifications": notifications,
    }


def _prune_ttl_cache(
    cache: dict[Any, tuple[float, Any]],
    *,
    max_entries: int,
) -> None:
    if max_entries <= 0:
        cache.clear()
        return
    overflow = len(cache) - max_entries
    if overflow <= 0:
        return
    for key, _ in sorted(cache.items(), key=lambda item: float(item[1][0]))[:overflow]:
        cache.pop(key, None)


def _build_cached_base_context_bundle(db: Session, user_id: int, *, workspace: str) -> dict[str, Any]:
    workspace_norm = _normalize_workspace(workspace)
    if _AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS <= 0 or _AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES <= 0:
        return _build_context_bundle(db, user_id, workspace=workspace_norm, query="")

    cache_key = (int(user_id), workspace_norm)
    now = time.monotonic()
    with _base_context_cache_lock:
        hit = _base_context_cache.get(cache_key)
        if hit is not None:
            ts, cached_bundle = hit
            if (now - float(ts)) <= _AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS and isinstance(cached_bundle, dict):
                return cached_bundle
            _base_context_cache.pop(cache_key, None)

    bundle = _build_context_bundle(db, user_id, workspace=workspace_norm, query="")
    with _base_context_cache_lock:
        _base_context_cache[cache_key] = (now, bundle)
        _prune_ttl_cache(_base_context_cache, max_entries=_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES)
    return bundle


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


def _fetch_local_focus_citations(
    *,
    user_id: int,
    query: str,
    max_citations: int,
) -> tuple[list[AelinCitation], str]:
    local_db = create_session()
    try:
        n = max(4, min(20, int(max_citations or 6) * 2))
        focus_items = _memory.build_focus_items(local_db, user_id, query=query, limit=n)
        rows = [serialize_focus_item(item) for item in focus_items]
        return _to_citations(rows, max_citations), ""
    except Exception as exc:
        return [], str(exc)[:140]
    finally:
        try:
            local_db.close()
        except Exception:
            pass


def _hydrate_citation_avatars(
    db: Session,
    user_id: int,
    citations: list[AelinCitation],
) -> list[AelinCitation]:
    missing_ids = [int(it.message_id) for it in citations if not it.sender_avatar_url and int(it.message_id or 0) > 0]
    if not missing_ids:
        return citations

    rows = db.execute(
        select(Message.id, Contact.avatar_url)
        .join(Contact, Contact.id == Message.contact_id)
        .where(
            Message.user_id == user_id,
            Contact.user_id == user_id,
            Message.id.in_(missing_ids),
        )
    ).all()
    avatar_by_message_id: dict[int, str] = {}
    for message_id, avatar_url in rows:
        if avatar_url:
            avatar_by_message_id[int(message_id)] = str(avatar_url)

    if not avatar_by_message_id:
        return citations

    out: list[AelinCitation] = []
    for it in citations:
        if it.sender_avatar_url:
            out.append(it)
            continue
        avatar = avatar_by_message_id.get(int(it.message_id or 0))
        if avatar:
            out.append(it.model_copy(update={"sender_avatar_url": avatar}))
        else:
            out.append(it)
    return out


def _rule_based_answer(
    query: str,
    summary: str,
    citations: list[AelinCitation],
    *,
    brief_summary: str = "",
    todo_titles: list[str] | None = None,
    image_count: int = 0,
) -> str:
    image_tip = (
        f"\n\n你上传了 {image_count} 张图片。当前规则模式不具备图片理解能力，若需图像分析请配置支持视觉的模型。"
        if image_count > 0
        else ""
    )
    if not citations:
        todo_line = ""
        if todo_titles:
            todo_line = "\n\n你当前待跟进事项：\n" + "\n".join(f"- {title}" for title in todo_titles[:4])
        if summary:
            return (
                "我已在你的长期记忆中检索相关内容，但当前缺少足够的新证据。"
                f"\n\n当前记忆摘要：{_summarizer.summarize(summary)}"
                + (f"\n\n今日简报：{brief_summary}" if brief_summary else "")
                + todo_line
                + "\n\n建议：扩大追踪边界或先触发一次同步。"
                + image_tip
            )
        return (
            "当前还没有足够的信号证据。先连接数据源并同步后，我就能给出可追溯结论。"
            + (f"\n\n今日简报：{brief_summary}" if brief_summary else "")
            + todo_line
            + image_tip
        )

    top = citations[0]
    bullets = [
        f"- [{it.source_label}] {it.title}（{it.sender}，{it.received_at}）"
        for it in citations[:4]
    ]
    return (
        f"基于你最近的信号证据，和“{query.strip()}”最相关的线索是：\n"
        + "\n".join(bullets)
        + f"\n\n当前优先关注：{top.title}"
        + ("\n\n我也参考了你的长期记忆摘要。" if summary else "")
        + (f"\n\n今日简报：{brief_summary}" if brief_summary else "")
        + (
            "\n\n建议先处理待跟进事项：\n" + "\n".join(f"- {title}" for title in (todo_titles or [])[:3])
            if todo_titles
            else ""
        )
        + image_tip
    )


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


def _build_planner_memory_snapshot(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    include_file_memory: bool = True,
) -> dict[str, Any]:
    # Only file-memory retrieval remains here; legacy autonomy is gone.
    workspace_norm = _normalize_workspace(workspace)
    memory_hits: list[Any] = []
    if include_file_memory:
        memory_hits = _file_memory.search(
            user_id=user_id,
            workspace=workspace_norm,
            query=query,
            limit=12,
        )
    file_items = [
        {
            "path": item.path,
            "title": item.title,
            "preview": item.preview,
            "score": float(item.score),
            "updated_at": item.updated_at,
            "canonical_id": item.canonical_id,
            "target": item.target,
            "source": item.source,
            "kind": item.kind,
            "topic_path": item.topic_path,
            "entry_kind": item.entry_kind,
        }
        for item in memory_hits[:12]
    ]
    return {
        "active_items": [],
        "matched_items": [],
        "active_count": 0,
        "matched_count": len(file_items),
        "matched_file_items": file_items[:8],
        "matched_file_count": len(file_items),
    }


def _persist_web_search_results(
    db: Session,
    user_id: int,
    *,
    query: str,
    results: list[WebSearchResult],
) -> list[AelinCitation]:
    if not results:
        return []
    contact = crud.upsert_contact(db, user_id=user_id, handle="web:search", display_name="Web Search")
    now = datetime.now(timezone.utc)
    citations: list[AelinCitation] = []
    for idx, item in enumerate(results[:_WEB_SEARCH_MAX_RESULTS]):
        title = (item.title or "").strip()[:220]
        url = (item.url or "").strip()
        snippet = (item.snippet or "").strip()
        fetched = (getattr(item, "fetched_excerpt", "") or "").strip()
        if fetched and len(snippet) < 120:
            snippet = fetched
        snippet = snippet[:2200]
        if not title or not url:
            continue
        external_id = f"web:{hashlib.sha1(url.encode('utf-8')).hexdigest()}"
        body = f"{snippet}\n\nURL: {url}\n查询: {query.strip()[:180]}"
        msg = crud.create_message(
            db,
            user_id=user_id,
            contact_id=contact.id,
            source="web",
            external_id=external_id,
            sender=_domain_from_url(url),
            subject=title,
            body=body,
            received_at=now,
            summary=snippet or title,
        )
        if msg is not None and getattr(msg, "id", None) is None:
            db.flush()
        if msg is None:
            msg = db.scalar(
                select(Message).where(
                    Message.user_id == user_id,
                    Message.source == "web",
                    Message.external_id == external_id,
                )
            )
        if msg is None:
            continue
        crud.touch_contact_last_message(db, contact=contact, received_at=now)
        citations.append(
            AelinCitation(
                message_id=int(msg.id),
                source="web",
                source_label="Web",
                sender=_domain_from_url(url),
                sender_avatar_url=None,
                title=title,
                received_at=now.strftime("%Y-%m-%d %H:%M"),
                score=max(0.2, 6.0 - float(idx)),
            )
        )
    if citations:
        db.flush()
        content_tagging.enqueue_tagging_job(
            user_id=user_id,
            message_ids=[int(item.message_id) for item in citations],
            allow_llm=True,
        )
    return citations


def _enforce_answer_first(
    *,
    query: str,
    answer: str,
    citations: list[AelinCitation],
    web_results: list[WebSearchResult],
    memory_summary: str,
    brief_summary: str,
    todo_titles: list[str] | None = None,
    image_count: int = 0,
    allow_web_fallback: bool = True,
) -> str:
    text = (answer or "").strip()
    if text and not _looks_like_non_answer(text):
        return text
    if citations:
        return _rule_based_answer(
            query,
            memory_summary,
            citations,
            brief_summary=brief_summary,
            todo_titles=todo_titles or [],
            image_count=image_count,
        )
    if allow_web_fallback and web_results:
        guarded = _compose_web_first_answer(query, web_results)
        if guarded:
            return guarded
    return _rule_based_chat_answer(query, memory_summary=memory_summary, brief_summary=brief_summary)

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


def _get_memory_summary_for_chat(db: Session, user_id: int) -> str:
    return str(_memory.get_summary(db, user_id) or "")


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
    forced_intent = ""
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
    memory_summary = _get_memory_summary_for_chat(db, current_user.id)
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
            if persist_memory and payload.use_memory and answer:
                try:
                    _memory.update_after_turn(
                        db,
                        current_user.id,
                        [{"role": "user", "content": payload.query}],
                        answer,
                    )
                    db.commit()
                except Exception:
                    db.rollback()
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
    try:
        plane_snapshot = get_active_plane_task(current_user.id, workspace, plane="browser", db=db)
    except Exception:
        plane_snapshot = None
    if not (
        isinstance(plane_snapshot, dict)
        and plane_snapshot.get("task_id")
        and should_resume_active_plane_for_query(plane_snapshot, payload.query)
    ):
        plane_snapshot = None

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
        plane_snapshot=plane_snapshot,
        cancel_token=cancel_token,
    )

    trace_steps: list[AelinToolStep] = [*prefixed_traces]

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

    # 再把每一次工具调用显式映射为更细粒度阶段，便于前端展示完整工具链。
    for run in result.tool_runs:
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
        # 对 plane 工具按 action 细分阶段，方便 UI 展示 plane 链路。
        if run.name == "plane":
            action = str(run.args.get("action") or "").strip().lower()
            plane_name = str(run.args.get("plane") or "").strip() or "browser"
            state = str(run.result.get("state") or "").strip() if isinstance(run.result, dict) else ""
            task_id = str(run.args.get("task_id") or "").strip()
            if action == "delegate":
                stage = "plane_delegate"
                goal = str(run.args.get("goal") or "").strip()
                if not run.error and goal:
                    detail = f"delegate plane={plane_name} goal={goal[:120]}"
            elif action == "status":
                stage = "plane_status"
                if not run.error:
                    detail = f"status plane={plane_name} task_id={task_id or 'unknown'} state={state or 'unknown'}"
            elif action == "continue":
                stage = "plane_continue"
                if not run.error:
                    detail = f"continue plane={plane_name} task_id={task_id or 'unknown'} state={state or 'unknown'}"
            elif action == "close":
                stage = "plane_close"
                if not run.error:
                    detail = f"close plane={plane_name} task_id={task_id or 'unknown'}"
            elif action == "catalog":
                stage = "plane_catalog"
                if not run.error:
                    detail = f"catalog plane={plane_name}"

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
        try:
            _memory.update_after_turn(
                db,
                current_user.id,
                [{"role": "user", "content": payload.query}],
                result.answer,
            )
            db.commit()
        except Exception:
            db.rollback()

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
