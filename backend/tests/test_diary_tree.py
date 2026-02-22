from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.services.openviking_bridge import TrackingFileMemoryBridge
from app.settings import settings


def test_diary_tree_and_search_include_topic_metadata(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(settings, "openviking_enabled", True)
        monkeypatch.setattr(settings, "openviking_data_dir", str(Path(tmpdir)))
        bridge = TrackingFileMemoryBridge()

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
