from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from deepagents import create_deep_agent
from deepagents.backends.state import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_core.tools import Tool

from app.services.aelin_tools import AelinToolHub
from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage
from app.services.llm import LLMService


def build_chat_tools(
    *,
    tool_hub: AelinToolHub,
    policy: AelinToolPolicy,
) -> tuple[list[Tool], list[dict[str, Any]], ToolPolicyUsage]:
    """
    Build the set of DeepAgents tools and return them together with
    an empty tool_runs list and a shared ToolPolicyUsage tracker.

    This function is intentionally light-weight and only depends on
    AelinToolHub for actual capability execution; DeepAgents sees a
    flat list of tools.
    """
    usage = ToolPolicyUsage()
    tool_runs: list[dict[str, Any]] = []

    def _make_tool(name: str, description: str) -> Tool:
        def _call_tool(*params: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal usage
            if params and not kwargs and isinstance(params[0], dict):
                kwargs = params[0]
            args = dict(kwargs or {})
            decision = policy.evaluate(name=name, args=args, usage=usage)
            from time import perf_counter

            started = perf_counter()
            if not decision.allowed:
                latency_ms = int((perf_counter() - started) * 1000)
                tool_runs.append(
                    {
                        "round_index": 1,
                        "name": name,
                        "args": args,
                        "status": "denied",
                        "result": {"ok": False, "error": decision.reason},
                        "error": decision.reason,
                        "is_write": decision.is_write,
                        "latency_ms": latency_ms,
                    }
                )
                return {"ok": False, "error": decision.reason}

            result = tool_hub.execute(name, args)
            latency_ms = int((perf_counter() - started) * 1000)
            usage.round_calls += 1
            usage.total_calls += 1
            if decision.is_write:
                usage.write_calls += 1
            status = "completed" if bool(result.get("ok", True)) else "failed"
            error = "" if status == "completed" else str(result.get("error") or "")[:160]
            tool_runs.append(
                {
                    "round_index": 1,
                    "name": name,
                    "args": args,
                    "status": status,
                    "result": result,
                    "error": error,
                    "is_write": decision.is_write,
                    "latency_ms": latency_ms,
                }
            )
            return result

        return Tool.from_function(func=_call_tool, name=name, description=description)

    # DeepAgents 主图只暴露核心能力型工具，不再包含 memory/context/profile 等
    # 旧式记忆/画像入口；这些能力今后由 AGENTS.md + DeepAgents Memory 负责。
    tools: list[Tool] = []
    for td in tool_hub.tool_definitions():
        fn = td.get("function") if isinstance(td, dict) else None
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "").strip()
        desc = str(fn.get("description") or "").strip() or name
        if name in {
            "web_search",
            "attachment_search",
            "google_workspace",
            "device",
            "screen_get",
            "plane",
        }:
            tools.append(_make_tool(name, desc))

    return tools, tool_runs, usage


def build_chat_agent(
    *,
    service: LLMService,
    provider: str,
    tool_hub: AelinToolHub,
    policy: AelinToolPolicy,
    memory_summary: str,
    skills_root: Path | None = None,
) -> tuple[Any, ToolPolicyUsage, list[dict[str, Any]], dict[str, Any]]:
    """
    Construct a DeepAgents chat agent along with tool usage trackers and
    file mounts (skills + memory).

    Returns (agent, usage, tool_runs, files_mapping).
    """
    from app.services.deepagents_loop import _build_chat_model  # reuse model builder

    chat_model = _build_chat_model(service, provider)
    if chat_model is None:
        return None, ToolPolicyUsage(), [], {}

    tools, tool_runs, usage = build_chat_tools(tool_hub=tool_hub, policy=policy)

    system_prompt = (
        "You are Aelin running on DeepAgents. "
        "You see the conversation history and the latest user query. "
        "Answer the user directly in the same language as the query."
    )

    skills_root = skills_root or (Path(__file__).resolve().parent.parent / "deepagents_skills")
    skill_files: dict[str, str] = {}
    skill_sources: list[str] = []
    if skills_root.is_dir():
        for subdir in skills_root.iterdir():
            if not subdir.is_dir():
                continue
            rel_dir = f"/{subdir.name}/"
            skill_sources.append(rel_dir)
            for file_path in subdir.rglob("*.md"):
                try:
                    text = file_path.read_text(encoding="utf-8")
                except Exception:
                    continue
                rel_path = f"/{subdir.name}/{file_path.name}"
                skill_files[rel_path] = text

    memory_files: dict[str, str] = {}
    memory_paths: list[str] = []
    if memory_summary.strip():
        mem_text = memory_summary.strip()
        if mem_text.lstrip().startswith("#"):
            mem_body = mem_text
        else:
            mem_body_lines = [
                "# Aelin Session Memory",
                "",
                "## User summary",
                mem_text,
            ]
            mem_body = "\n".join(mem_body_lines)
        mem_path = "/memory/AGENTS.md"
        memory_files[mem_path] = mem_body
        memory_paths.append(mem_path)

    files: dict[str, Any] = {}
    for path, text in {**skill_files, **memory_files}.items():
        files[path] = create_file_data(text)

    agent = create_deep_agent(
        model=chat_model,
        system_prompt=system_prompt,
        backend=StateBackend,
        tools=tools,
        skills=skill_sources or None,
        memory=memory_paths or None,
    )

    return agent, usage, tool_runs, files
