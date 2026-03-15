from __future__ import annotations

from app.services.aelin_loop_message import build_initial_messages


def test_build_initial_messages_injects_skill_prompt_before_history():
    messages = build_initial_messages(
        query="帮我抓取这个文档页面",
        memory_summary="memory",
        history_turns=[{"role": "user", "content": "之前聊过 pinchtab"}],
        images=None,
        attachment_ids=None,
        forced_intent="",
        forced_tool_runs=None,
        tool_skill_bodies=[
            "[AELIN SKILL]\nname=Crawl4AI Web Ingestion\nslug=crawl4ai\n\n# Purpose\nUse Crawl4AI for ingestion."
        ],
    )

    system_contents = [str(row.get("content") or "") for row in messages if row.get("role") == "system"]
    assert any("[AELIN SKILL]" in text for text in system_contents)

    skill_index = next(i for i, row in enumerate(messages) if "[AELIN SKILL]" in str(row.get("content") or ""))
    history_index = next(i for i, row in enumerate(messages) if row.get("role") == "user" and row.get("content") == "之前聊过 pinchtab")
    assert skill_index < history_index


def test_build_initial_messages_injects_plane_resume_hint():
    messages = build_initial_messages(
        query="继续刚才的网页任务",
        memory_summary="memory",
        history_turns=None,
        images=None,
        attachment_ids=None,
        forced_intent="",
        forced_tool_runs=[
            {
                "name": "plane",
                "args": {"action": "status", "plane": "browser", "task_id": "task_1"},
                "result": {
                    "ok": True,
                    "plane": "browser",
                    "task_id": "task_1",
                    "state": "running",
                    "last_url": "https://x.com/home",
                    "summary": "已打开 X 并等待继续",
                },
            }
        ],
        tool_skill_bodies=None,
    )

    system_contents = [str(row.get("content") or "") for row in messages if row.get("role") == "system"]
    assert any("browser plane task" in text for text in system_contents)
    assert any('action="continue"' in text for text in system_contents)
