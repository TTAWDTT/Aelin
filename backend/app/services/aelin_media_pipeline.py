from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from app.routers.aelin_text_helpers import _infer_diary_topic_path
from app.services.agent_memory import AgentMemoryService
from app.services.media_ingest import MediaIngestOutput, MediaIngestService
from app.services.openviking_bridge import file_memory_bridge

memory_service = AgentMemoryService()
media_ingest_service = MediaIngestService()
file_memory = file_memory_bridge


def build_media_ingest_answer(result: MediaIngestOutput, *, written: bool) -> str:
    body = [
        f"我已读取并理解这个 {result.platform} 链接的内容。",
        "",
        result.summary.strip(),
    ]
    if written:
        body.extend(["", "已写入 Aelinの日记，可作为后续 RAG 上下文使用。"])
    elif not result.quality_usable:
        body.extend(
            [
                "",
                (
                    f"本次未写入 Aelinの日记：内容质量门禁未通过"
                    f"（score={result.quality_score:.2f}，reason={result.quality_reason or 'quality_gate'}）。"
                ),
            ]
        )
    else:
        body.extend(["", "摘要已生成，但写入 Aelinの日记 失败。"])
    if result.limitations:
        body.extend(["", "限制说明："])
        body.extend([f"- {item}" for item in result.limitations[:3]])
    return "\n".join(body).strip()


def save_media_ingest_diary(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    result: MediaIngestOutput,
) -> dict[str, Any]:
    if not result.quality_usable:
        return {
            "written": False,
            "diary_path": "",
            "note_added": False,
            "skip_reason": result.quality_reason or "quality_gate_rejected",
            "quality_score": float(result.quality_score),
        }

    target = SimpleNamespace(
        user_id=user_id,
        workspace=workspace,
        source_type=result.platform,
        track_type="url",
        source_key=result.canonical_url,
        display_name=result.title or result.canonical_url,
    )
    topic_path = _infer_diary_topic_path(
        result.title,
        result.summary_overview,
        result.information_note,
        fallback_source=result.platform or "媒体",
    )
    source_indices = [
        {
            "type": "url",
            "label": result.title[:220] or result.canonical_url[:220],
            "url": result.canonical_url[:500],
        }
    ]
    out_path = file_memory.append_insight(
        target=target,
        title=result.insight_title,
        markdown=result.insight_markdown,
        reason=result.reason,
        confidence=result.confidence,
        source_query=result.canonical_url,
        topic_path=topic_path,
        source_indices=source_indices,
        entry_kind="media_insight",
    )
    diary_path = str(out_path) if out_path is not None else ""
    written = bool(diary_path)
    note_added = False
    if written:
        try:
            memory_service.add_note(
                db,
                user_id,
                f"[Aelinの日记] {result.insight_title}\npath: {diary_path}\nsource: {result.platform}",
                kind="memory_insight",
                source=f"media:{result.platform}",
            )
            note_added = True
        except Exception:
            note_added = False
    return {
        "written": written,
        "diary_path": diary_path,
        "note_added": note_added,
        "skip_reason": ("" if written else "file_write_failed"),
        "quality_score": float(result.quality_score),
    }
