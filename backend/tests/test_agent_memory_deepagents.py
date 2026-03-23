from __future__ import annotations

from app.services.aelin.context_service import build_context_bundle
from app.services.memory.agent_memory import AgentMemoryService


SAMPLE_AGENTS_MD = """# Aelin Session Memory

## 会话摘要
这一两天主要聊了 NBA 和 DeepAgents 重构。

## 长期记忆
- [事实] Aelin 使用 DeepAgents 作为唯一 agent loop。
- [偏好] 用户喜欢详细的链路展示。

## 待办
- [-] 补充 DeepAgents 记忆测试用例
- [!] 清理旧的 DB 记忆残留
"""


class _DummySession:
    """Lightweight stand-in for a SQLAlchemy Session.

    AgentMemoryService in DeepAgents 模式下只依赖 AGENTS.md 投影，
    因此这里不会真正触发任何 DB 操作。
    """

    pass


class _FakeMemoryService(AgentMemoryService):
    def _read_agents_md_text(self, user_id: int, workspace: str = "default") -> str:  # type: ignore[override]
        return SAMPLE_AGENTS_MD


def test_context_bundle_projects_from_agents_md() -> None:
    mem = _FakeMemoryService()
    bundle = build_context_bundle(
        db=_DummySession(),
        user_id=1,
        workspace="default",
        query="",
        memory_service=mem,
    )

    summary = bundle["summary"]
    assert "DeepAgents 重构" in summary

    notes = bundle["notes"]
    assert bundle["notes_count"] == len(notes) > 0
    assert any("Aelin 使用 DeepAgents 作为唯一 agent loop" in n.content for n in notes)

    todos = bundle["todos"]
    assert todos

    layers = bundle["memory_layers"]
    assert layers.facts or layers.preferences or layers.in_progress


