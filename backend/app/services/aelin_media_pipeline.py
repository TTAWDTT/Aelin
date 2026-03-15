from __future__ import annotations

from app.services.media_ingest import MediaIngestOutput, MediaIngestService

media_ingest_service = MediaIngestService()


def build_media_ingest_answer(result: MediaIngestOutput) -> str:
    body = [
        f"我已读取并理解这个 {result.platform} 链接的内容。",
        "",
        result.summary.strip(),
    ]
    if result.quality_usable and not result.needs_review:
        body.extend(
            [
                "",
                "本次摘要仅用于当前结果展示，当前不会自动写入长期记忆。",
            ]
        )
    else:
        body.extend(
            [
                "",
                (
                    f"本次摘要仅用于当前结果展示，未进入长期记忆：质量门禁未通过"
                    f"（score={result.quality_score:.2f}，reason={result.quality_reason or 'quality_gate'}）。"
                ),
            ]
        )
    if result.limitations:
        body.extend(["", "限制说明："])
        body.extend([f"- {item}" for item in result.limitations[:3]])
    return "\n".join(body).strip()
