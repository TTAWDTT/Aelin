from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from app.schemas import AelinCitation
from app.services.agent_memory import AgentMemoryService
from app.services.aelin_chat_planning import _normalize_match_text
from app.services.aelin_runtime import (
    json_from_text as _json_from_text,
    normalize_workspace as _normalize_workspace,
)
from app.services.llm import LLMService
from app.services.memory_draft import ParallelMemoryDraftResult
from app.services.openviking_bridge import tracking_file_memory_bridge
from app.settings import settings
from app.routers.aelin_text_helpers import (
    _build_chat_diary_entry,
    _build_source_indices_from_citations,
    _extract_first_json_object,
    _infer_diary_topic_path,
    _sanitize_diary_answer,
)

_memory = AgentMemoryService()
_tracking_file_memory = tracking_file_memory_bridge

def _save_chat_diary_entry(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    answer: str,
    citations: list[AelinCitation],
) -> dict[str, Any]:
    if not query.strip() or not answer.strip():
        return {"written": False, "reason": "empty_turn", "path": ""}
    now = datetime.now(timezone.utc)
    topic_path = ["与主人的聊天日记", now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")]
    title, markdown = _build_chat_diary_entry(query, answer, citations)
    target = SimpleNamespace(
        user_id=user_id,
        workspace=workspace,
        source_type="chat",
        track_type="conversation",
        source_key=f"chat:{now.strftime('%Y-%m-%d')}",
        display_name="与主人的聊天日记",
    )
    source_indices = _build_source_indices_from_citations(citations)
    out_path = _tracking_file_memory.append_insight(
        target=target,
        title=title,
        markdown=markdown,
        reason="chat_diary",
        confidence=0.82,
        source_query=query,
        topic_path=topic_path,
        source_indices=source_indices,
        entry_kind="chat_diary",
    )
    if out_path is None:
        return {"written": False, "reason": "file_write_failed", "path": ""}
    try:
        _memory.add_note(
            db,
            user_id,
            f"[chat-diary] {title}\npath: {str(out_path)}",
            kind="tracking_insight",
            source="chat:diary",
        )
    except Exception:
        pass
    return {"written": True, "reason": "", "path": str(out_path)}

def _save_parallel_draft_entry(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    answer: str,
    draft_result: ParallelMemoryDraftResult | None,
    quality_passed: bool,
) -> dict[str, Any]:
    if draft_result is None:
        return {"written": False, "reason": "draft_missing", "path": ""}
    if not quality_passed:
        return {"written": False, "reason": "verifier_not_passed", "path": ""}
    min_conf = max(0.0, min(1.0, float(getattr(settings, "aelin_parallel_memory_draft_min_confidence", 0.58) or 0.58)))
    if float(draft_result.confidence or 0.0) < min_conf:
        return {"written": False, "reason": "draft_low_confidence", "path": ""}
    if int(draft_result.evidence_count or 0) <= 0:
        return {"written": False, "reason": "draft_no_evidence", "path": ""}

    now = datetime.now(timezone.utc)
    query_text = re.sub(r"\s+", " ", str(query or "").strip())[:320]
    topic_path = [
        *(draft_result.topic_path[:4] if isinstance(draft_result.topic_path, list) and draft_result.topic_path else ["并行记忆"]),
        now.strftime("%Y"),
        now.strftime("%m"),
        now.strftime("%d"),
    ]
    source_key = f"parallel:{now.strftime('%Y-%m-%d')}:{hashlib.sha1(query_text.encode('utf-8')).hexdigest()[:16]}"
    target = SimpleNamespace(
        user_id=user_id,
        workspace=workspace,
        source_type="chat",
        track_type="conversation",
        source_key=source_key,
        display_name="并行记忆草稿",
    )
    source_indices = []
    seen_refs: set[str] = set()
    for row in (draft_result.source_indices or [])[:24]:
        if not isinstance(row, dict):
            continue
        source_type = str(row.get("type") or "unknown").strip()[:32]
        label = str(row.get("label") or "").strip()[:220]
        message_id = int(row.get("message_id") or 0)
        path = str(row.get("path") or "").strip()[:500]
        url = str(row.get("url") or "").strip()[:500]
        dedupe_key = f"{source_type}:{message_id}:{path}:{url}:{label}".lower()
        if dedupe_key in seen_refs:
            continue
        seen_refs.add(dedupe_key)
        source_indices.append(
            {
                "type": source_type,
                "label": label,
                "message_id": message_id,
                "path": path,
                "url": url,
            }
        )
    source_indices.insert(
        0,
        {
            "type": "query",
            "label": query_text[:220],
            "message_id": 0,
            "path": "",
            "url": "",
        },
    )
    merged_markdown = "\n".join(
        [
            draft_result.markdown.strip(),
            "",
            "## 最终回答归档",
            "",
            _sanitize_diary_answer(answer),
        ]
    ).strip()
    out_path = _tracking_file_memory.append_insight(
        target=target,
        title=str(draft_result.title or "并行记忆草稿")[:120],
        markdown=merged_markdown,
        reason="parallel_draft_commit",
        confidence=float(draft_result.confidence or 0.0),
        source_query=query_text,
        topic_path=topic_path,
        source_indices=source_indices[:28],
        entry_kind="chat_parallel_draft",
    )
    if out_path is None:
        return {"written": False, "reason": "file_write_failed", "path": ""}
    try:
        _memory.add_note(
            db,
            user_id,
            f"[parallel-draft] {draft_result.title}\npath: {str(out_path)}",
            kind="tracking_insight",
            source="chat:parallel-draft",
        )
    except Exception:
        pass
    return {"written": True, "reason": "", "path": str(out_path)}

def _pick_tracking_target_for_insight(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    tracking_snapshot: dict[str, Any] | None,
) -> TrackingTarget | None:
    workspace_norm = _normalize_workspace(workspace)
    try:
        rows = _tracking.list_targets(
            db,
            user_id=user_id,
            workspace=workspace_norm,
            limit=180,
            include_deleted=False,
        )
    except Exception:
        rows = []
    if not rows:
        return None

    candidates: list[tuple[str, str, str]] = []
    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}
    for key in ("matched_items", "active_items"):
        items = tracking.get(key)
        if not isinstance(items, list):
            continue
        for item in items[:16]:
            if not isinstance(item, dict):
                continue
            target = str(item.get("target") or "").strip()
            if not target:
                continue
            source = _normalize_track_source(str(item.get("source") or "auto"))
            candidate_query = str(item.get("query") or "").strip()
            candidates.append((source, target, candidate_query))

    q_norm = _normalize_match_text(query)
    best: TrackingTarget | None = None
    best_score = -1.0
    for row in rows:
        if row is None:
            continue
        if str(getattr(row, "status", "") or "").strip().lower() == "deleted":
            continue
        if getattr(row, "deleted_at", None) is not None:
            continue
        row_source = str(getattr(row, "source_type", "web") or "web").strip().lower() or "web"
        row_target = (str(getattr(row, "display_name", "") or "") or str(getattr(row, "source_key", "") or "")).strip()
        row_cfg = _json_from_text(getattr(row, "config_json", "") or "{}")
        row_query = str(row_cfg.get("query") or "").strip()
        row_target_norm = _normalize_match_text(row_target)
        row_query_norm = _normalize_match_text(row_query)

        score = 0.0
        if str(getattr(row, "status", "") or "").strip().lower() == "active":
            score += 1.2

        for source, target, cand_query in candidates:
            target_norm = _normalize_match_text(target)
            cand_query_norm = _normalize_match_text(cand_query)
            if source and source == row_source:
                score += 0.7
            if target_norm and row_target_norm and (target_norm in row_target_norm or row_target_norm in target_norm):
                score += 3.2
            if cand_query_norm and row_query_norm and (cand_query_norm in row_query_norm or row_query_norm in cand_query_norm):
                score += 1.8

        if q_norm:
            if row_target_norm and (q_norm in row_target_norm or row_target_norm in q_norm):
                score += 2.0
            if row_query_norm and (q_norm in row_query_norm or row_query_norm in q_norm):
                score += 1.4

        if score > best_score:
            best_score = score
            best = row

    if best is not None and best_score > 0:
        return best
    return rows[0] if rows else None

def _decide_tracking_insight_write(
    *,
    service: LLMService,
    provider: str,
    query: str,
    answer: str,
    tracking_snapshot: dict[str, Any] | None,
    file_memory_lines: list[str],
) -> dict[str, Any]:
    if provider == "rule_based" or not service.is_configured():
        return {"should_write": False, "reason": "llm_not_configured", "confidence": 0.0}
    question = (query or "").strip()
    reply = (answer or "").strip()
    if not question or not reply:
        return {"should_write": False, "reason": "empty_turn", "confidence": 0.0}

    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}
    active_items = tracking.get("active_items") if isinstance(tracking.get("active_items"), list) else []
    matched_items = tracking.get("matched_items") if isinstance(tracking.get("matched_items"), list) else []
    active_hint = "; ".join(str(it.get("target") or "").strip() for it in active_items[:8] if isinstance(it, dict) and str(it.get("target") or "").strip())
    matched_hint = "; ".join(str(it.get("target") or "").strip() for it in matched_items[:6] if isinstance(it, dict) and str(it.get("target") or "").strip())
    file_hint = "\n".join(file_memory_lines[:6]) if file_memory_lines else ""

    system_prompt = (
        "You are Aelin planner for long-term tracking memory write.\\n"
        "Decide autonomously whether this finished answer should be persisted as a tracking insight.\\n"
        "Return strict JSON only with keys: should_write, confidence, title, markdown, reason.\\n"
        "Rules: should_write=true only when output adds stable insight helpful for future discussion; markdown should be concise, structured, and factual.\\n"
        "confidence in [0,1]."
    )
    user_prompt = (
        f"question: {question[:500]}\\n\\n"
        + f"answer: {reply[:1800]}\\n\\n"
        + f"matched_tracking: {matched_hint or 'none'}\\n"
        + f"active_tracking: {active_hint or 'none'}\\n"
        + (f"file_memory_hits:\\n{file_hint}\\n" if file_hint else "")
    )
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=320,
            stream=False,
        )
    except Exception as exc:
        return {"should_write": False, "reason": f"planner_error:{str(exc)[:80]}", "confidence": 0.0}

    parsed = _extract_first_json_object(str(raw or ""))
    should_write = bool(parsed.get("should_write"))
    title = str(parsed.get("title") or "").strip()[:120]
    markdown = str(parsed.get("markdown") or "").strip()[:3200]
    reason = str(parsed.get("reason") or "").strip()[:200]
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0.0)))
    except Exception:
        confidence = 0.0

    if should_write and not markdown:
        base_title = title or "追踪洞察"
        markdown = f"### {base_title}\\n\\n{reply[:1200]}"

    if should_write and not title:
        title = "追踪洞察"

    if (not should_write) and confidence >= 0.85 and markdown:
        # High-confidence insights are kept even if model forgot the boolean flag.
        should_write = True

    return {
        "should_write": should_write,
        "confidence": confidence,
        "title": title,
        "markdown": markdown,
        "reason": reason or ("planner_declined" if not should_write else ""),
    }

def _maybe_write_tracking_insight(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    answer: str,
    service: LLMService,
    provider: str,
    tracking_snapshot: dict[str, Any] | None,
    file_memory_lines: list[str],
    citations: list[AelinCitation],
) -> dict[str, Any]:
    decision = _decide_tracking_insight_write(
        service=service,
        provider=provider,
        query=query,
        answer=answer,
        tracking_snapshot=tracking_snapshot,
        file_memory_lines=file_memory_lines,
    )
    if not bool(decision.get("should_write")):
        return {"written": False, "reason": str(decision.get("reason") or "planner_skip")}

    target = _pick_tracking_target_for_insight(
        db,
        user_id=user_id,
        workspace=workspace,
        query=query,
        tracking_snapshot=tracking_snapshot,
    )
    if target is None:
        return {"written": False, "reason": "no_tracking_target"}

    topic_path = _infer_diary_topic_path(
        query,
        answer,
        str(getattr(target, "display_name", "") or ""),
        fallback_source=str(getattr(target, "source_type", "") or "综合"),
    )
    source_indices = _build_source_indices_from_citations(citations)
    out_path = _tracking_file_memory.append_insight(
        target=target,
        title=str(decision.get("title") or "追踪洞察"),
        markdown=str(decision.get("markdown") or "").strip(),
        reason=str(decision.get("reason") or ""),
        confidence=float(decision.get("confidence") or 0.0),
        source_query=query,
        topic_path=topic_path,
        source_indices=source_indices,
        entry_kind="tracking_insight",
    )
    if out_path is None:
        return {"written": False, "reason": "file_write_failed"}

    try:
        _memory.add_note(
            db,
            user_id,
            f"[tracking-insight] {str(decision.get('title') or '追踪洞察')}\\npath: {str(out_path)}",
            kind="tracking_insight",
            source=f"tracking:insight:{int(getattr(target, 'id', 0) or 0)}",
        )
    except Exception:
        pass

    return {
        "written": True,
        "target_id": int(getattr(target, "id", 0) or 0),
        "target": str(getattr(target, "display_name", "") or ""),
        "path": str(out_path),
        "confidence": float(decision.get("confidence") or 0.0),
        "reason": str(decision.get("reason") or ""),
    }
