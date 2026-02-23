from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.services.openviking_bridge import TrackingFileMemoryBridge
from app.settings import settings


def test_diary_tree_and_search_include_topic_metadata(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(settings, "openviking_enabled", True)
        monkeypatch.setattr(settings, "openviking_data_dir", str(Path(tmpdir)))
        bridge = TrackingFileMemoryBridge()
        # Force deterministic local lexical path for unit assertions.
        bridge._openviking = None

        target = SimpleNamespace(
            user_id=1,
            workspace="default",
            source_type="web",
            track_type="term",
            source_key="Stephen Curry",
            display_name="Stephen Curry",
        )
        out_path = bridge.append_insight(
            target=target,
            title="Stephen Curry 近况",
            markdown="## 今日对话\n\nStephen Curry 本周状态回升，三分命中率回暖。",
            reason="unit-test",
            confidence=0.9,
            source_query="NBA 最近如何",
            topic_path=["体育", "NBA", "球员"],
            source_indices=[{"type": "message", "message_id": 42, "label": "消息源"}],
            entry_kind="tracking_insight",
        )
        assert out_path is not None
        assert "diary" in str(out_path).lower()
        assert "nba" in str(out_path).lower()

        hits = bridge.search(user_id=1, workspace="default", query="curry", limit=10, source=None)
        assert hits
        assert any("体育" in (hit.topic_path or "") for hit in hits)
        assert any((hit.entry_kind or "") == "tracking_insight" for hit in hits)

        tree = bridge.list_diary_tree(user_id=1, workspace="default", max_files=100)
        assert tree
        top_names = [node.name for node in tree]
        assert "体育" in top_names


def test_search_excludes_chat_diary_unless_explicitly_enabled(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(settings, "openviking_enabled", True)
        monkeypatch.setattr(settings, "openviking_data_dir", str(Path(tmpdir)))
        bridge = TrackingFileMemoryBridge()

        chat_target = SimpleNamespace(
            user_id=1,
            workspace="default",
            source_type="chat",
            track_type="conversation",
            source_key="chat:test",
            display_name="与主人的聊天日记",
        )
        tracking_target = SimpleNamespace(
            user_id=1,
            workspace="default",
            source_type="web",
            track_type="term",
            source_key="deepseek",
            display_name="DeepSeek",
        )

        diary_token = "zz_diary_only_token_123"
        rag_token = "zz_rag_token_456"
        chat_path = bridge.append_insight(
            target=chat_target,
            title="聊天纪要",
            markdown=f"## 今日对话\n\n{diary_token}",
            reason="unit-test",
            confidence=0.8,
            source_query="chat query",
            topic_path=["与主人的聊天日记"],
            source_indices=[],
            entry_kind="chat_diary",
        )
        rag_path = bridge.append_insight(
            target=tracking_target,
            title="追踪洞察",
            markdown=f"## Insight\n\n{rag_token}",
            reason="unit-test",
            confidence=0.9,
            source_query="tracking query",
            topic_path=["技术", "模型"],
            source_indices=[],
            entry_kind="tracking_insight",
        )
        assert chat_path is not None
        assert rag_path is not None

        hits_without_diary = bridge.search(
            user_id=1,
            workspace="default",
            query=diary_token,
            limit=10,
            include_diary=False,
        )
        assert hits_without_diary == []

        hits_with_diary = bridge.search(
            user_id=1,
            workspace="default",
            query=diary_token,
            limit=10,
            include_diary=True,
        )
        assert hits_with_diary
        assert any((hit.entry_kind or "") == "chat_diary" for hit in hits_with_diary)

        rag_hits = bridge.search(
            user_id=1,
            workspace="default",
            query=rag_token,
            limit=10,
            include_diary=False,
        )
        assert rag_hits
        assert any((hit.entry_kind or "") == "tracking_insight" for hit in rag_hits)


def test_append_insight_writes_human_diary_content_and_sidecar(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(settings, "openviking_enabled", True)
        monkeypatch.setattr(settings, "openviking_data_dir", str(Path(tmpdir)))
        bridge = TrackingFileMemoryBridge()
        bridge._openviking = None

        target = SimpleNamespace(
            user_id=1,
            workspace="default",
            source_type="chat",
            track_type="conversation",
            source_key="chat:daily",
            display_name="与主人的聊天日记",
        )
        out_path = bridge.append_insight(
            target=target,
            title="聊天纪要：今天聊模型",
            markdown="## 今日对话\n\n今天我们聊了模型迭代节奏，也确认了后续跟踪点。",
            reason="unit-test",
            confidence=0.88,
            source_query="今天聊了什么",
            topic_path=["与主人的聊天日记", "模型讨论"],
            source_indices=[{"type": "message", "message_id": 7, "label": "聊天消息"}],
            entry_kind="chat_diary",
        )
        assert out_path is not None
        diary_path = Path(out_path)
        diary_text = diary_path.read_text(encoding="utf-8")
        assert "今天我们聊了模型迭代节奏" in diary_text
        assert "- canonical_id:" not in diary_text
        assert "- source_indices_json:" not in diary_text
        assert "后续如果有新的变化，我会继续补写。" not in diary_text
        assert "## 今日对话" not in diary_text

        sidecar_path = diary_path.with_suffix(".meta.json")
        assert sidecar_path.exists()
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert sidecar.get("entry_kind") == "chat_diary"
        assert sidecar.get("title") == "聊天纪要：今天聊模型"
        assert isinstance(sidecar.get("source_indices"), list) and sidecar.get("source_indices")


def test_chat_diary_rollup_merges_closed_day_and_cleans_raw(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(settings, "openviking_enabled", True)
        monkeypatch.setattr(settings, "openviking_data_dir", str(Path(tmpdir)))
        bridge = TrackingFileMemoryBridge()
        bridge._openviking = None

        target = SimpleNamespace(
            user_id=1,
            workspace="default",
            source_type="chat",
            track_type="conversation",
            source_key="chat:rollup",
            display_name="与主人的聊天日记",
        )

        monkeypatch.setattr(
            "app.services.openviking_bridge._utcnow",
            lambda: datetime(2026, 2, 22, 14, 30, tzinfo=timezone.utc),
        )
        first = bridge.append_insight(
            target=target,
            title="第一条",
            markdown="今天第一条记录",
            reason="unit-test",
            confidence=0.8,
            source_query="q1",
            topic_path=["与主人的聊天日记"],
            source_indices=[],
            entry_kind="chat_diary",
        )
        assert first is not None

        monkeypatch.setattr(
            "app.services.openviking_bridge._utcnow",
            lambda: datetime(2026, 2, 23, 9, 5, tzinfo=timezone.utc),
        )
        second = bridge.append_insight(
            target=target,
            title="第二条",
            markdown="今天第二条记录",
            reason="unit-test",
            confidence=0.8,
            source_query="q2",
            topic_path=["与主人的聊天日记"],
            source_indices=[],
            entry_kind="chat_diary",
        )
        assert second is not None

        root = Path(tmpdir) / "users" / "1" / "workspaces" / "default" / "diary"
        daily_file = root / "daily" / "2026" / "02" / "2026-02-22.md"
        assert daily_file.exists()
        assert "今天第一条记录" in daily_file.read_text(encoding="utf-8")

        old_raw_dir = root / "raw" / "2026" / "02" / "22"
        assert not old_raw_dir.exists()

        today_raw_dir = root / "raw" / "2026" / "02" / "23"
        assert today_raw_dir.exists()
        assert any(today_raw_dir.glob("*.md"))
