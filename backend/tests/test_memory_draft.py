from __future__ import annotations

from pathlib import Path

import app.routers.aelin as aelin_router
from app.services.memory_draft import ParallelMemoryDraftResult, build_parallel_memory_draft


def test_parallel_memory_draft_builds_structured_markdown():
    result = build_parallel_memory_draft(
        query="NBA最近如何？",
        citations=[
            {
                "message_id": 101,
                "source": "local",
                "source_label": "本地",
                "sender": "ESPN",
                "title": "Warriors 130-119 Spurs",
                "snippet": "Curry scored 30 points with 6 threes.",
            }
        ],
        file_memory_items=[
            {
                "path": "/tmp/diary/nba.md",
                "title": "NBA 日记",
                "preview": "勇士近期进攻效率回升，库里手感明显恢复。",
                "topic_path": "体育 > NBA",
            }
        ],
        web_results=[
            {
                "title": "NBA Scores Today",
                "url": "https://example.com/nba-scores",
                "host": "example.com",
                "snippet": "Latest game results and injury report.",
            }
        ],
        memory_summary="你长期关注 NBA 和勇士。",
        brief_summary="今日有 6 场比赛。",
    )
    assert isinstance(result, ParallelMemoryDraftResult)
    assert result.evidence_count >= 3
    assert result.confidence >= 0.4
    assert result.topic_path
    assert "并行提炼（草稿）" in result.markdown
    assert any((row.get("type") == "message") for row in result.source_indices)
    assert any((row.get("type") == "file") for row in result.source_indices)
    assert any((row.get("type") == "url") for row in result.source_indices)


def test_save_parallel_draft_entry_writes_when_quality_passed(monkeypatch, tmp_path: Path):
    draft = ParallelMemoryDraftResult(
        title="并行记忆草稿：NBA最近如何",
        markdown="## 并行提炼（草稿）\n\n勇士状态回升。",
        confidence=0.88,
        topic_path=["体育", "NBA"],
        source_indices=[{"type": "message", "message_id": 123, "label": "box score", "path": "", "url": ""}],
        evidence_count=3,
        reason="parallel_draft_ready",
    )

    out_path = tmp_path / "parallel-draft.md"
    monkeypatch.setattr(aelin_router._file_memory, "append_insight", lambda **kwargs: out_path)
    monkeypatch.setattr(aelin_router._memory, "add_note", lambda *args, **kwargs: None)

    result = aelin_router._save_parallel_draft_entry(
        object(),
        user_id=1,
        workspace="default",
        query="NBA最近如何",
        answer="勇士近期状态回升，库里手感恢复。",
        draft_result=draft,
        quality_passed=True,
    )
    assert result.get("written") is True
    assert str(result.get("path") or "").endswith("parallel-draft.md")


def test_save_parallel_draft_entry_skips_on_quality_gate():
    draft = ParallelMemoryDraftResult(
        title="并行记忆草稿",
        markdown="x",
        confidence=0.9,
        topic_path=["对话"],
        source_indices=[],
        evidence_count=1,
        reason="parallel_draft_ready",
    )
    result = aelin_router._save_parallel_draft_entry(
        object(),
        user_id=1,
        workspace="default",
        query="test",
        answer="test",
        draft_result=draft,
        quality_passed=False,
    )
    assert result.get("written") is False
    assert result.get("reason") == "verifier_not_passed"
