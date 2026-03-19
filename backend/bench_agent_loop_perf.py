from __future__ import annotations

import argparse
import copy
import json
import math
import statistics
import threading
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from app.services.aelin_agent_loop import AelinAgentLoop
from app.services.aelin_tool_policy import AelinToolPolicy


def _tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"id": call_id, "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}


class _BenchCompletions:
    def __init__(self, rounds: list[dict[str, Any]], llm_latency_ms: list[int] | None = None) -> None:
        self._rounds = list(rounds)
        self._idx = 0
        self._latency_ms = list(llm_latency_ms or [])
        self.calls: list[dict[str, Any]] = []
        self.call_metrics: list[dict[str, float]] = []

    def _pick_latency_ms(self) -> int:
        if not self._latency_ms:
            return 0
        idx = min(max(0, self._idx), len(self._latency_ms) - 1)
        return max(0, int(self._latency_ms[idx]))

    def create(self, **kwargs):
        started = time.perf_counter()
        call_payload = copy.deepcopy(kwargs)
        self.calls.append(call_payload)
        latency_ms = self._pick_latency_ms()
        if latency_ms > 0:
            time.sleep(latency_ms / 1000.0)

        idx = min(self._idx, len(self._rounds) - 1)
        self._idx += 1
        row = self._rounds[idx] if self._rounds else {}
        if row.get("raise"):
            raise RuntimeError(str(row.get("raise")))

        tool_calls = []
        for tc in row.get("tool_calls", []):
            tool_calls.append(
                SimpleNamespace(
                    id=str(tc.get("id") or ""),
                    function=SimpleNamespace(
                        name=str(tc.get("name") or ""),
                        arguments=str(tc.get("arguments") or "{}"),
                    ),
                )
            )
        msg = SimpleNamespace(content=str(row.get("content") or ""), tool_calls=tool_calls)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        messages = call_payload.get("messages")
        msg_chars = len(json.dumps(messages, ensure_ascii=False)) if isinstance(messages, list) else 0
        self.call_metrics.append(
            {
                "elapsed_ms": elapsed_ms,
                "messages_chars": float(msg_chars),
                "tools_count": float(len(list(call_payload.get("tools") or []))),
            }
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _BenchToolHub:
    def __init__(self, *, tool_latency_ms: dict[str, int], heavy_items: int = 12) -> None:
        self.workspace = "default"
        self._tool_latency_ms = {str(k): max(0, int(v)) for k, v in (tool_latency_ms or {}).items()}
        self._heavy_items = max(3, int(heavy_items))
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def tool_definitions(self) -> list[dict[str, Any]]:
        names = [
            "context_get",
            "diary",
            "profile",
            "web_search",
            "screen_get",
            "browser_state_get",
            "browser_use",
        ]
        return [{"type": "function", "function": {"name": n, "parameters": {"type": "object"}}} for n in names]

    def _sleep_for(self, name: str) -> None:
        ms = max(0, int(self._tool_latency_ms.get(str(name), 0)))
        if ms > 0:
            time.sleep(ms / 1000.0)

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        safe_name = str(name or "").strip().lower()
        started = time.perf_counter()
        with self._lock:
            self.events.append({"type": "start", "name": safe_name, "ts": started})
        self._sleep_for(safe_name)
        ended = time.perf_counter()
        with self._lock:
            self.events.append({"type": "end", "name": safe_name, "ts": ended})

        if safe_name == "context_get":
            return {
                "ok": True,
                "summary": "这是用于压测的上下文摘要。",
                "focus_items": [
                    {"title": f"focus-{i}", "source": "x", "url": f"https://x.com/{i}", "snippet": "s" * 240}
                    for i in range(self._heavy_items)
                ],
                "todos": [{"title": f"todo-{i}", "detail": "d" * 200} for i in range(self._heavy_items)],
            }
        if safe_name == "diary":
            return {
                "ok": True,
                "items": [{"title": f"note-{i}", "path": f"/d/{i}.md", "preview": "p" * 300} for i in range(self._heavy_items)],
                "total": self._heavy_items,
            }
        if safe_name == "profile":
            return {"ok": True, "note_id": 1, "summary": "profile note written"}
        if safe_name == "web_search":
            return {
                "ok": True,
                "query": str(args.get("query") or ""),
                "providers": ["bing_html", "duckduckgo_lite", "google_news_rss"],
                "items": [
                    {
                        "title": f"result-{i}",
                        "url": f"https://example.com/{i}",
                        "snippet": "snippet-" + ("x" * 520),
                        "provider": "bing_html",
                        "source": "web",
                    }
                    for i in range(self._heavy_items)
                ],
                "total": self._heavy_items,
            }
        if safe_name == "screen_get":
            return {
                "ok": True,
                "data_url": "data:image/png;base64,AAA",
                "name": "bench.png",
                "width": 1280,
                "height": 720,
                "source_display": "display-1",
            }
        if safe_name == "browser_state_get":
            return {
                "ok": True,
                "scope": "cdp",
                "url": "https://x.com/home",
                "title": "X",
                "interactive_targets": [{"name": f"btn-{i}", "role": "button"} for i in range(self._heavy_items)],
            }
        if safe_name == "browser_use":
            return {
                "ok": True,
                "action": str(args.get("action") or ""),
                "scope": str(args.get("scope") or "auto"),
                "effect_summary": "browser step completed",
                "requires_confirmation": False,
            }
        return {"ok": True}


def _fake_service(rounds: list[dict[str, Any]], llm_latency_ms: list[int]) -> Any:
    completions = _BenchCompletions(rounds=rounds, llm_latency_ms=llm_latency_ms)
    return SimpleNamespace(
        config=SimpleNamespace(model="bench-model", temperature=0.0),
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        _completions=completions,
    )


@dataclass
class BenchScenario:
    name: str
    description: str
    rounds: list[dict[str, Any]]
    llm_latency_ms: list[int]
    tool_latency_ms: dict[str, int]
    query: str
    memory_summary: str
    history_turns: list[dict[str, str]]
    images: list[dict[str, str]]


def _build_scenarios() -> list[BenchScenario]:
    return [
        BenchScenario(
            name="core_read_write",
            description="读批处理+一次写入",
            rounds=[
                {
                    "tool_calls": [
                        _tool_call("c1", "context_get", {"query": "x"}),
                        _tool_call("c2", "diary", {"action": "search", "query": "x"}),
                        _tool_call("c3", "profile", {"action": "append_note", "note": "n"}),
                    ]
                },
                {"content": "已完成。"},
            ],
            llm_latency_ms=[260, 220],
            tool_latency_ms={"context_get": 45, "diary": 60, "profile": 75},
            query="总结并记下重点",
            memory_summary="用户关注 AI 生态动态",
            history_turns=[
                {"role": "user", "content": "最近有什么新消息？"},
                {"role": "assistant", "content": "我可以先做检索。"},
            ],
            images=[],
        ),
        BenchScenario(
            name="browser_multi_step",
            description="浏览器两步动作后收敛回答",
            rounds=[
                {"tool_calls": [_tool_call("b1", "browser_use", {"action": "navigate", "url": "https://x.com", "scope": "auto"})]},
                {"tool_calls": [_tool_call("b2", "browser_use", {"action": "click", "target": "Profile", "scope": "cdp"})]},
                {"content": "已进入主页并完成分析。"},
            ],
            llm_latency_ms=[320, 300, 220],
            tool_latency_ms={"browser_use": 130},
            query="打开 X 进入我的主页并分析关注列表",
            memory_summary="",
            history_turns=[],
            images=[],
        ),
        BenchScenario(
            name="web_heavy_payload",
            description="高负载 web_search 返回大结果集",
            rounds=[
                {
                    "tool_calls": [
                        _tool_call(
                            "w1",
                            "web_search",
                            {"action": "search_and_fetch", "query": "OpenAI 发布会后续动态", "max_results": 12, "fetch_top_k": 4},
                        )
                    ]
                },
                {"content": "我已整理出关键线索。"},
            ],
            llm_latency_ms=[280, 220],
            tool_latency_ms={"web_search": 180},
            query="请帮我联网检索并整理 OpenAI 发布会后续动态",
            memory_summary="用户偏好直接结论",
            history_turns=[
                {"role": "user", "content": "尽量给我直接结论。"},
                {"role": "assistant", "content": "好的，我先联网抓取。"},
            ],
            images=[],
        ),
    ]


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    seq = sorted(float(v) for v in values)
    idx = max(0, min(len(seq) - 1, math.ceil(len(seq) * 0.95) - 1))
    return float(seq[idx])


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def _run_once(scenario: BenchScenario) -> dict[str, float]:
    service = _fake_service(rounds=scenario.rounds, llm_latency_ms=scenario.llm_latency_ms)
    tool_hub = _BenchToolHub(tool_latency_ms=scenario.tool_latency_ms, heavy_items=12)
    loop = AelinAgentLoop(
        service=service,
        provider="openai",
        tool_hub=tool_hub,
        policy=AelinToolPolicy(
            max_calls_per_round=3,
            max_tool_calls=8,
            max_write_calls=3,
            allow_write_tools=True,
        ),
        max_rounds=6,
        round_timeout_seconds=20.0,
        total_timeout_seconds=60.0,
    )

    started = time.perf_counter()
    result = loop.run(
        query=scenario.query,
        memory_summary=scenario.memory_summary,
        history_turns=scenario.history_turns,
        images=scenario.images,
    )
    total_ms = (time.perf_counter() - started) * 1000.0
    llm_ms = sum(float(it.get("elapsed_ms") or 0.0) for it in service._completions.call_metrics)
    tool_ms = sum(float(run.latency_ms or 0.0) for run in result.tool_runs)
    message_chars = sum(float(it.get("messages_chars") or 0.0) for it in service._completions.call_metrics)
    overhead_ms = max(0.0, total_ms - llm_ms - tool_ms)
    return {
        "total_ms": total_ms,
        "llm_ms": llm_ms,
        "tool_ms": tool_ms,
        "overhead_ms": overhead_ms,
        "message_chars": message_chars,
        "rounds": float(result.rounds),
        "tool_calls": float(result.total_calls),
    }


def _summarize(samples: list[dict[str, float]]) -> dict[str, float]:
    keys = ["total_ms", "llm_ms", "tool_ms", "overhead_ms", "message_chars", "rounds", "tool_calls"]
    out: dict[str, float] = {}
    for key in keys:
        vals = [float(it.get(key) or 0.0) for it in samples]
        out[f"{key}_avg"] = _mean(vals)
        out[f"{key}_p95"] = _p95(vals)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Aelin Agent Loop performance benchmark")
    parser.add_argument("--iterations", type=int, default=12, help="Measured iterations per scenario (default: 12)")
    parser.add_argument("--warmup", type=int, default=2, help="Warmup iterations per scenario (default: 2)")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    iterations = max(1, int(args.iterations or 1))
    warmup = max(0, int(args.warmup or 0))
    scenarios = _build_scenarios()
    output: list[dict[str, Any]] = []

    for scenario in scenarios:
        for _ in range(warmup):
            _run_once(scenario)
        samples = [_run_once(scenario) for _ in range(iterations)]
        summary = _summarize(samples)
        row = {
            "name": scenario.name,
            "description": scenario.description,
            "iterations": iterations,
            **summary,
        }
        output.append(row)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    print("Aelin Agent Loop Perf Benchmark")
    print(f"scenarios={len(output)} iterations={iterations} warmup={warmup}")
    print("-" * 110)
    print(
        f"{'scenario':20} {'total(avg/p95)':22} {'llm(avg)':10} {'tool(avg)':10} "
        f"{'overhead(avg)':14} {'msg_chars(avg)':14} {'rounds(avg)':10}"
    )
    print("-" * 110)
    for row in output:
        print(
            f"{str(row['name'])[:20]:20} "
            f"{row['total_ms_avg']:7.1f}/{row['total_ms_p95']:7.1f}   "
            f"{row['llm_ms_avg']:10.1f} "
            f"{row['tool_ms_avg']:10.1f} "
            f"{row['overhead_ms_avg']:14.1f} "
            f"{row['message_chars_avg']:14.0f} "
            f"{row['rounds_avg']:10.2f}"
        )
    print("-" * 110)


if __name__ == "__main__":
    main()

