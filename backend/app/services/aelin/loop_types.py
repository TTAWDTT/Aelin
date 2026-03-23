from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


# Common stop_reason values for AelinAgentLoopResult. Keeping them in one place
# avoids scattered string literals across core and DeepAgents bridge code.
STOP_REASON_CANCELLED = "cancelled"


@dataclass
class AgentLoopToolRun:
    call_index: int
    name: str
    args: dict[str, Any]
    status: str
    result: dict[str, Any]
    error: str = ""
    is_write: bool = False
    latency_ms: int = 0


@dataclass
class AgentLoopTraceStep:
    stage: str
    status: str
    detail: str = ""
    count: int = 0
    ts: int = field(default_factory=now_ms)


@dataclass
class AelinAgentLoopResult:
    ok: bool
    answer: str
    stop_reason: str
    total_calls: int
    write_calls: int
    tool_runs: list[AgentLoopToolRun]
    trace_steps: list[AgentLoopTraceStep]
    actions: list[dict[str, str]]
    error: str = ""
    # Optional snapshot of the agent's memory file (e.g. /memory/AGENTS.md)
    memory_snapshot: str = ""
