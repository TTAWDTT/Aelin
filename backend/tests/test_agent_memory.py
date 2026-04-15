from __future__ import annotations

import json

from app.services.memory.agent_memory import AgentMemoryService
from app.services.memory.file_memory_bridge import file_memory_bridge


def _memory_dir(root, *, user_id: int, workspace: str):
    return root / "users" / str(user_id) / "workspaces" / workspace / "memory"


def test_agent_memory_bundle_writes_projection_files_and_index(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    file_memory_bridge.write_agents_memory(
        user_id=7,
        workspace="demo",
        content="\n".join(
            [
                "# Aelin Session Memory",
                "",
                "## 会话摘要",
                "当前重点是 memory_search 和 compact memory bundle。",
                "",
                "## 长期记忆",
                "- [偏好] 偏好简洁中文回复。",
                "- [事实] 当前在推进 artifact delivery。",
                "- [项目] OpenClaw memory refactor。",
                "",
                "## 待办",
                "- [!] 跑一次完整测试",
                "",
            ]
        ),
    )

    bundle = service.get_memory_bundle(
        user_id=7,
        workspace="demo",
        query_hint="OpenClaw memory refactor",
    )

    assert "/memory/AGENTS.md" in bundle["files"]
    assert "/memory/preferences.md" in bundle["files"]
    assert "/memory/facts.md" in bundle["files"]
    assert "/memory/projects.md" in bundle["files"]
    assert "/memory/todos.md" in bundle["files"]
    assert "/memory/memory_index.json" in bundle["files"]
    assert "当前问题相关记忆" in bundle["prompt_text"]
    assert "/memory/projects.md" in bundle["memory_paths"]

    memory_dir = _memory_dir(tmp_path, user_id=7, workspace="demo")
    assert (memory_dir / "preferences.md").is_file()
    assert (memory_dir / "facts.md").is_file()
    assert (memory_dir / "projects.md").is_file()
    assert (memory_dir / "todos.md").is_file()
    index_payload = json.loads((memory_dir / "memory_index.json").read_text(encoding="utf-8"))
    assert index_payload["counts"]["projects"] == 1
    assert any(item["path"] == "/memory/projects.md" for item in index_payload["files"])


def test_agent_memory_search_respects_kind_filters(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    file_memory_bridge.write_agents_memory(
        user_id=9,
        workspace="demo",
        content="\n".join(
            [
                "# Aelin Session Memory",
                "",
                "## 长期记忆",
                "- [偏好] 偏好简洁中文回复。",
                "- [事实] 用户正在处理 write_file 稳定性。",
                "- [项目] DeepAgents memory alignment。",
                "",
                "## 待办",
                "- [!] 跑一次完整测试",
                "",
            ]
        ),
    )

    preference_hits = service.search_memory(
        user_id=9,
        workspace="demo",
        query="简洁 中文 回复",
        kinds=["preference"],
        top_k=3,
    )
    todo_hits = service.search_memory(
        user_id=9,
        workspace="demo",
        query="完整 测试",
        kinds=["todo"],
        top_k=3,
    )

    assert preference_hits
    assert preference_hits[0]["kind"] == "preference"
    assert preference_hits[0]["path"] == "/memory/preferences.md"
    assert todo_hits
    assert todo_hits[0]["kind"] == "todo"
    assert todo_hits[0]["path"] == "/memory/todos.md"
