from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DeepAgentsRunContext:
    user_id: int | None = None
    workspace: str = "default"
    attachment_ids: list[int] = field(default_factory=list)
    source: str = "chat_ui"
