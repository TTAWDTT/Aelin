from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from app.services.agent_memory import AgentMemoryService
from app.services.llm import LLMService
from app.services.memory_draft import ParallelMemoryDraftResult
from app.services.openviking_bridge import file_memory_bridge
from app.settings import settings
from app.routers.aelin_text_helpers import (
    _build_source_indices_from_citations,
    _extract_first_json_object,
)

_memory = AgentMemoryService()
_file_memory = file_memory_bridge

_MEMORY_FINAL_ANSWER_MAX_CHARS = 2800
_CODE_BLOCK_RE = re.compile(r"```.*?```", flags=re.S)


def _sanitize_memory_answer(value: str, *, max_chars: int = _MEMORY_FINAL_ANSWER_MAX_CHARS) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _CODE_BLOCK_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text[:max_chars].strip()

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
            _sanitize_memory_answer(answer),
        ]
    ).strip()
    out_path = _file_memory.append_insight(
        target=target,
        title=str(draft_result.title or "并行记忆草稿")[:120],
        markdown=merged_markdown,
        reason="parallel_draft_commit",
        confidence=float(draft_result.confidence or 0.0),
        source_query=query_text,
        topic_path=topic_path,
        source_indices=source_indices[:28],
        entry_kind="memory_insight",
    )
    if out_path is None:
        return {"written": False, "reason": "file_write_failed", "path": ""}
    return {"written": True, "reason": "", "path": str(out_path)}

def _decide_memory_insight_write(
    *,
    service: LLMService,
    provider: str,
    query: str,
    answer: str,
    memory_snapshot: dict[str, Any] | None,
    file_memory_lines: list[str],
) -> dict[str, Any]:
    if provider == "rule_based" or not service.is_configured():
        return {"should_write": False, "reason": "llm_not_configured", "confidence": 0.0}
    question = (query or "").strip()
    reply = (answer or "").strip()
    if not question or not reply:
        return {"should_write": False, "reason": "empty_turn", "confidence": 0.0}

    memory = memory_snapshot if isinstance(memory_snapshot, dict) else {}
    active_items = memory.get("active_items") if isinstance(memory.get("active_items"), list) else []
    matched_items = memory.get("matched_items") if isinstance(memory.get("matched_items"), list) else []
    active_hint = "; ".join(str(it.get("target") or "").strip() for it in active_items[:8] if isinstance(it, dict) and str(it.get("target") or "").strip())
    matched_hint = "; ".join(str(it.get("target") or "").strip() for it in matched_items[:6] if isinstance(it, dict) and str(it.get("target") or "").strip())
    file_hint = "\n".join(file_memory_lines[:6]) if file_memory_lines else ""

    system_prompt = (
        "You are Aelin planner for long-term memory write.\\n"
        "Decide autonomously whether this finished answer should be persisted as a reusable memory insight.\\n"
        "Return strict JSON only with keys: should_write, confidence, title, markdown, reason.\\n"
        "Rules: should_write=true only when output adds stable insight helpful for future discussion; markdown should be concise, structured, and factual.\\n"
        "confidence in [0,1]."
    )
    user_prompt = (
        f"question: {question[:500]}\\n\\n"
        + f"answer: {reply[:1800]}\\n\\n"
        + f"matched_memory: {matched_hint or 'none'}\\n"
        + f"active_memory: {active_hint or 'none'}\\n"
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
