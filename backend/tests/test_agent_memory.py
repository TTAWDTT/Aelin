from __future__ import annotations

import json
from pathlib import Path

from app.services.memory.agent_memory import AgentMemoryService
from app.services.memory.file_memory_bridge import file_memory_bridge


def _memory_dir(root, *, user_id: int, workspace: str):
    return root / "users" / str(user_id) / "workspaces" / workspace / "memory"


def test_agent_memory_persists_structured_store_and_agents_projection(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    service.append_fact_to_memory(
        user_id=7,
        workspace="demo",
        content="Lives in Shanghai and owns the remote-control branch.",
    )
    service.append_preference_to_memory(
        user_id=7,
        workspace="demo",
        content="Prefers concise Chinese replies.",
    )
    service.add_todo_to_memory(
        user_id=7,
        workspace="demo",
        title="Run a full remote-control regression pass",
        priority="high",
    )
    inserted = service.add_note(
        None,  # type: ignore[arg-type]
        7,
        "Stabilizing the Anthology handoff.",
        kind="in_progress",
        workspace="demo",
    )

    memory_dir = _memory_dir(tmp_path, user_id=7, workspace="demo")
    agents_path = memory_dir / "AGENTS.md"
    store_path = memory_dir / "_structured_memory.json"
    profile_path = memory_dir / "PROFILE.md"
    facts_path = memory_dir / "FACTS.md"
    preferences_path = memory_dir / "PREFERENCES.md"
    todos_path = memory_dir / "TODOS.md"
    index_path = memory_dir / "INDEX.json"

    assert inserted.kind == "in_progress"
    assert agents_path.is_file()
    assert store_path.is_file()
    assert profile_path.is_file()
    assert facts_path.is_file()
    assert preferences_path.is_file()
    assert todos_path.is_file()
    assert index_path.is_file()

    store = json.loads(store_path.read_text(encoding="utf-8"))
    assert store["version"] == 3
    assert [row["kind"] for row in store["notes"]] == ["fact", "preference", "in_progress"]
    assert store["todos"][0]["priority"] == "high"

    agents_text = agents_path.read_text(encoding="utf-8")
    assert "## Summary" in agents_text
    assert "## Preferences" in agents_text
    assert "## Long-term Memory" in agents_text
    assert "- [fact] Lives in Shanghai and owns the remote-control branch." in agents_text
    assert "Prefers concise Chinese replies." in agents_text
    assert "Stabilizing the Anthology handoff." in agents_text
    assert "- [!] Run a full remote-control regression pass" in agents_text
    assert "/memory/INDEX.json" in agents_text

    projected = service.get_agents_memory_text(None, 7, workspace="demo")  # type: ignore[arg-type]
    assert "Long-term Memory" in projected
    assert "Current Focus" in projected

    notes = service.list_notes(None, 7, workspace="demo")  # type: ignore[arg-type]
    assert [row.kind for row in notes] == ["in_progress", "preference", "fact"]

    todos = service.list_todos(None, 7, workspace="demo", include_done=False)  # type: ignore[arg-type]
    assert len(todos) == 1
    assert todos[0]["priority"] == "high"

    bundle = service.get_memory_bundle(user_id=7, workspace="demo")
    assert "/memory/AGENTS.md" in bundle["files"]
    assert "/memory/FACTS.md" in bundle["files"]
    assert "/memory/PREFERENCES.md" in bundle["files"]
    assert "/memory/TODOS.md" in bundle["files"]

    hits = service.search_memory(user_id=7, workspace="demo", query="Shanghai remote-control branch", top_k=4)
    assert hits
    assert hits[0]["kind"] in {"fact", "recent_context"}
    assert any(hit["path"] == "/memory/FACTS.md" for hit in hits)


def test_agent_memory_migrates_existing_agents_md_on_first_structured_write(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    memory_dir = _memory_dir(tmp_path, user_id=9, workspace="legacy")
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Aelin Session Memory",
                "",
                "## Summary",
                "Recent focus is Feishu and QQ remote-control stabilization.",
                "",
                "## Long-term Memory",
                "- [fact] User name is Yixiao.",
                "- [preference] Prefer Chinese-first replies.",
                "",
                "## Todos",
                "- [!] Verify Feishu bot end-to-end.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    created = service.add_note(
        None,  # type: ignore[arg-type]
        9,
        "Read-only tools need retry safety.",
        kind="fact",
        workspace="legacy",
    )

    store = json.loads((memory_dir / "_structured_memory.json").read_text(encoding="utf-8"))
    assert created.kind == "fact"
    assert store["summary"]["content"] == "Recent focus is Feishu and QQ remote-control stabilization."
    assert [row["kind"] for row in store["notes"]] == ["fact", "preference", "fact"]
    assert store["todos"][0]["title"] == "Verify Feishu bot end-to-end."

    agents_text = service.get_agents_memory_text(None, 9, workspace="legacy")  # type: ignore[arg-type]
    assert "Read-only tools need retry safety." in agents_text
    assert "Prefer Chinese-first replies." in agents_text
    assert "Verify Feishu bot end-to-end." in agents_text

    summary = service.get_summary(None, 9, workspace="legacy")  # type: ignore[arg-type]
    assert summary == "Recent focus is Feishu and QQ remote-control stabilization."


def test_agent_memory_supports_profile_projects_and_filtered_search(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    profile = service.upsert_profile_fields(
        user_id=11,
        workspace="memory-lab",
        fields={
            "name": "Yixiao",
            "language": "Chinese first, English okay when needed",
            "working_preferences": "Prefers concrete implementation over abstract planning.",
        },
    )
    project = service.upsert_project(
        user_id=11,
        workspace="memory-lab",
        project={
            "name": "OpenClaw-style memory refactor",
            "status": "active",
            "summary": "Replace giant prompt stuffing with compact projection plus retrieval.",
            "tags": ["memory", "performance"],
        },
    )
    service.add_note(
        None,  # type: ignore[arg-type]
        11,
        "Current focus is shipping memory_search and compact AGENTS projection.",
        kind="in_progress",
        workspace="memory-lab",
    )

    assert profile["fields"]["name"] == "Yixiao"
    assert project is not None
    assert project["name"] == "OpenClaw-style memory refactor"

    profile_hits = service.search_memory(
        user_id=11,
        workspace="memory-lab",
        query="Chinese first replies",
        kinds=["profile"],
        top_k=3,
    )
    assert profile_hits
    assert profile_hits[0]["path"] == "/memory/PROFILE.md"

    project_hits = service.search_memory(
        user_id=11,
        workspace="memory-lab",
        query="compact projection retrieval memory",
        kinds=["project"],
        top_k=3,
    )
    assert project_hits
    assert project_hits[0]["path"] == "/memory/PROJECTS.md"


def test_agent_memory_dedupes_duplicate_writes_and_merges_projects(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    service.append_fact_to_memory(user_id=13, workspace="dedupe", content="User prefers remote-control debugging.")
    service.append_fact_to_memory(user_id=13, workspace="dedupe", content="User prefers remote control debugging.")
    service.append_preference_to_memory(user_id=13, workspace="dedupe", content="Reply in Chinese first.")
    service.append_preference_to_memory(user_id=13, workspace="dedupe", content="Reply in Chinese first.")
    service.add_note(None, 13, "Track the CI regression work.", kind="note", workspace="dedupe")  # type: ignore[arg-type]
    service.add_note(None, 13, "Track the CI regression work.", kind="note", workspace="dedupe")  # type: ignore[arg-type]
    service.add_todo_to_memory(user_id=13, workspace="dedupe", title="Run frontend vitest", priority="normal")
    service.add_todo_to_memory(user_id=13, workspace="dedupe", title="Run frontend vitest", priority="high")
    service.upsert_project(
        user_id=13,
        workspace="dedupe",
        project={
            "name": "Memory refactor",
            "status": "active",
            "summary": "Compact prompt injection",
            "tags": ["memory"],
        },
    )
    project = service.upsert_project(
        user_id=13,
        workspace="dedupe",
        project={
            "name": "memory-refactor",
            "status": "active",
            "detail": "Add ranking, compaction, and recovery.",
            "tags": ["performance", "memory"],
        },
    )

    assert project is not None

    store_path = _memory_dir(tmp_path, user_id=13, workspace="dedupe") / "_structured_memory.json"
    store = json.loads(store_path.read_text(encoding="utf-8"))

    assert [row["kind"] for row in store["notes"]] == ["fact", "preference", "note"]
    assert len(store["todos"]) == 1
    assert store["todos"][0]["priority"] == "high"
    assert len(store["projects"]) == 1
    assert sorted(store["projects"][0]["tags"]) == ["memory", "performance"]
    assert "ranking" in store["projects"][0]["detail"].lower()


def test_agent_memory_recovers_corrupt_store_from_agents_projection(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    memory_dir = _memory_dir(tmp_path, user_id=15, workspace="recover")
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "_structured_memory.json").write_text("{not-valid-json", encoding="utf-8")
    (memory_dir / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Aelin Session Memory",
                "",
                "## Summary",
                "Recover Feishu memory after the store broke.",
                "",
                "## Long-term Memory",
                "- [fact] User is Yixiao.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    bundle = service.get_memory_bundle(user_id=15, workspace="recover")

    assert "Recover Feishu memory after the store broke." in bundle["prompt_text"]
    assert "User is Yixiao." in bundle["prompt_text"]

    store = json.loads((memory_dir / "_structured_memory.json").read_text(encoding="utf-8"))
    assert store["summary"]["content"] == "Recover Feishu memory after the store broke."
    assert store["meta"]["recovered_from_corrupt_store_at"]

    backups = list(Path(memory_dir).glob("_structured_memory.corrupt.*.json"))
    assert backups
    assert backups[0].read_text(encoding="utf-8") == "{not-valid-json"


def test_agent_memory_bundle_cache_reuses_projection_until_store_changes(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    service.append_fact_to_memory(
        user_id=17,
        workspace="cache",
        content="Prefers compact runtime prompts.",
    )

    calls = {"count": 0}
    original = service._projection_files_from_store

    def _wrapped_projection(store):  # noqa: ANN001
        calls["count"] += 1
        return original(store)

    monkeypatch.setattr(service, "_projection_files_from_store", _wrapped_projection)
    service._clear_memory_bundle_cache_for_scope(user_id=17, workspace="cache")

    first = service.get_memory_bundle(user_id=17, workspace="cache")
    second = service.get_memory_bundle(user_id=17, workspace="cache")

    assert first["prompt_text"] == second["prompt_text"]
    assert calls["count"] == 1

    service.append_preference_to_memory(
        user_id=17,
        workspace="cache",
        content="Use memory_search before reading full files.",
    )
    third = service.get_memory_bundle(user_id=17, workspace="cache")

    assert "memory_search" in third["prompt_text"]
    assert calls["count"] == 2


def test_agent_memory_search_prefers_active_project_matches(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    service.upsert_project(
        user_id=19,
        workspace="search-rank",
        project={
            "name": "Memory performance refactor",
            "status": "active",
            "summary": "Improve ranking and compact runtime injection.",
            "tags": ["memory", "performance"],
        },
    )
    service.add_note(
        None,  # type: ignore[arg-type]
        19,
        "Memory refactor is generally important.",
        kind="fact",
        workspace="search-rank",
    )

    hits = service.search_memory(
        user_id=19,
        workspace="search-rank",
        query="memory performance ranking",
        top_k=4,
    )

    assert hits
    assert hits[0]["kind"] == "project"
    assert hits[0]["path"] == "/memory/PROJECTS.md"


def test_agent_memory_bundle_uses_query_hint_for_relevant_paths(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    service.upsert_project(
        user_id=21,
        workspace="bundle-query",
        project={
            "name": "Remote control stabilization",
            "status": "active",
            "summary": "Keep QQ and Feishu remote control reliable.",
            "tags": ["remote-control", "qq"],
        },
    )
    service.append_fact_to_memory(
        user_id=21,
        workspace="bundle-query",
        content="User owns the remote-control branch.",
    )

    bundle = service.get_memory_bundle(
        user_id=21,
        workspace="bundle-query",
        query_hint="qq remote control stabilization",
    )

    assert "Query-Relevant Memory" in bundle["prompt_text"]
    assert "/memory/PROJECTS.md" in bundle["memory_paths"]


def test_agent_memory_search_candidate_cache_reuses_rows_until_store_changes(monkeypatch, tmp_path):
    service = AgentMemoryService()
    monkeypatch.setattr(file_memory_bridge, "root", tmp_path)
    file_memory_bridge.clear_cache_for_tests()

    service.append_fact_to_memory(
        user_id=23,
        workspace="search-cache",
        content="Feishu bot uses long connection mode.",
    )

    calls = {"count": 0}
    original = service._search_candidate_rows_from_store

    def _wrapped_candidates(store):  # noqa: ANN001
        calls["count"] += 1
        return original(store)

    monkeypatch.setattr(service, "_search_candidate_rows_from_store", _wrapped_candidates)
    service._clear_search_candidate_cache()

    first = service.search_memory(user_id=23, workspace="search-cache", query="feishu long connection", top_k=3)
    second = service.search_memory(user_id=23, workspace="search-cache", query="feishu long connection", top_k=3)

    assert first
    assert second
    assert calls["count"] == 1

    service.append_preference_to_memory(
        user_id=23,
        workspace="search-cache",
        content="Prefer Feishu tests before QQ tests.",
    )
    third = service.search_memory(user_id=23, workspace="search-cache", query="feishu tests", top_k=3)

    assert third
    assert calls["count"] == 2
