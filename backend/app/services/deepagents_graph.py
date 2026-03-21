from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from deepagents import create_deep_agent
from deepagents.backends.state import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_core.tools import Tool, StructuredTool
from pydantic import BaseModel, Field

from app.services.aelin_tools import AelinToolHub, _result_error
from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage
from app.services.llm import LLMService
from app.services.tools_web import tool_web_search
from app.services.tools_files import tool_attachment_search
from app.services.tools_gws import tool_google_workspace
from app.services.tools_device import tool_device, tool_screen_get


class DeviceToolInput(BaseModel):
    """
    Structured input schema for the unified `device` tool.

    We intentionally keep `action` as a free string here and rely on the
    underlying `tool_device` implementation to return a clear
    "unsupported device action" error for unknown actions, instead of
    failing Pydantic validation before the tool has a chance to respond.
    """

    action: str = Field(
        ...,
        description="Device action to perform. Allowed values: "
        "'status', 'open_url', 'open_aelin'. Other values will result in "
        "an 'unsupported device action' error.",
    )
    url: str | None = Field(
        default=None,
        description="HTTP or HTTPS URL to open when action == 'open_url'.",
    )
    route: str | None = Field(
        default=None,
        description="Optional route to activate when action == 'open_aelin', "
        "for example '/'.",
    )


def build_chat_tools(
    *,
    tool_hub: AelinToolHub,
    policy: AelinToolPolicy,
) -> tuple[list[Tool], list[dict[str, Any]], ToolPolicyUsage]:
    """
    Build the set of DeepAgents-native tools and return them together with
    an empty tool_runs list and a shared ToolPolicyUsage tracker.

    与其在 tool wrapper 里再次调用 ``tool_hub.execute(name, args)``，这里直接
    绑定到每个领域的能力函数（tools_web/tools_files/tools_gws/...），这样
    DeepAgents 看到的是“真正的能力工具”，而不是 Aelin ToolHub 的二次壳。
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

            if name == "web_search":
                result = tool_web_search(tool_hub, args)
            elif name == "attachment_search":
                result = tool_attachment_search(tool_hub, args)
            elif name == "google_workspace":
                result = tool_google_workspace(tool_hub, args)
            elif name == "device":
                result = tool_device(tool_hub, args)
            elif name == "screen_get":
                result = tool_screen_get(tool_hub, args)
            else:
                # This should not happen because we only register a fixed
                # allowlist of names below, but keep a defensive fallback so
                # that DeepAgents 得到清晰的错误而不是爆栈。
                result = _result_error(f"unsupported_deepagents_tool:{name}")
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

    def _make_device_tool(description: str) -> Tool:
        """
        Structured wrapper for the unified `device` tool.

        The underlying function accepts a single `DeviceToolInput` payload so
        that DeepAgents / LangChain treat this as a StructuredTool instead of
        a single-string tool. This avoids the
        "Too many arguments to single-input tool device" error and gives the
        model a clear JSON schema for constructing arguments.
        """

        def _run_device(action: str, url: str | None = None, route: str | None = None) -> dict[str, Any]:
            nonlocal usage
            from time import perf_counter

            args: dict[str, Any] = {"action": str(action or "").strip()}
            if url is not None and str(url).strip():
                args["url"] = str(url).strip()
            if route is not None and str(route).strip():
                args["route"] = str(route).strip()

            decision = policy.evaluate(name="device", args=args, usage=usage)
            started = perf_counter()
            if not decision.allowed:
                latency_ms = int((perf_counter() - started) * 1000)
                tool_runs.append(
                    {
                        "round_index": 1,
                        "name": "device",
                        "args": args,
                        "status": "denied",
                        "result": {"ok": False, "error": decision.reason},
                        "error": decision.reason,
                        "is_write": decision.is_write,
                        "latency_ms": latency_ms,
                    }
                )
                return {"ok": False, "error": decision.reason}

            try:
                result = tool_device(tool_hub, args)
            except Exception as exc:  # noqa: BLE001
                result = _result_error(f"device_tool_failed:{str(exc)[:160]}")

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
                    "name": "device",
                    "args": args,
                    "status": status,
                    "result": result,
                    "error": error,
                    "is_write": decision.is_write,
                    "latency_ms": latency_ms,
                }
            )
            return result

        return StructuredTool.from_function(
            func=_run_device,
            name="device",
            description=description,
            args_schema=DeviceToolInput,
        )

    # DeepAgents 主图只暴露核心能力型工具，不再包含 memory/context/profile 等
    # 旧式记忆/画像入口；这些能力今后由 AGENTS.md + DeepAgents Memory 负责。
    tools: list[Tool] = []
    for td in tool_hub.tool_definitions():
        fn = td.get("function") if isinstance(td, dict) else None
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "").strip()
        desc = str(fn.get("description") or "").strip() or name

        if name == "web_search":
            # 约束 DeepAgents 使用的 web_search 契约，避免缺失 query 等常见错误。
            desc = (
                "Web search across the public internet.\n\n"
                "Required arguments:\n"
                '- \"action\": \"search\" or \"search_and_fetch\".\n'
                '- \"query\": non-empty string (Chinese or English). If missing or empty the tool will return '
                "\"missing query\".\n\n"
                "Optional arguments:\n"
                '- \"max_results\": integer in [1, 15], defaults to 15.\n'
                '- \"fetch_top_k\": integer in [0, 6], must be <= max_results; defaults to 3.\n\n'
                "Example calls:\n"
                '{"action": "search_and_fetch", "query": "最近三天的国际要闻", "max_results": 8, "fetch_top_k": 3}\n'
                '{"action": "search", "query": "DeepAgents architecture design", "max_results": 5}\n\n'
                "If you receive an error like \"missing query\" or \"unsupported action\", fix the arguments and "
                "call this tool again instead of repeating the same invalid call."
            )
        elif name == "device":
            # 统一 device 工具的契约，让 DeepAgents 知道允许的 action 以及参数要求。
            desc = (
                "Unified device tool for querying desktop status and opening URLs on the user's desktop.\n\n"
                "Allowed actions: \"status\", \"open_url\", \"open_aelin\".\n"
                "- \"status\": no extra arguments; returns platform, capabilities and desktop plugin status.\n"
                "- \"open_url\": requires a `url` string starting with http:// or https:// to open in the desktop browser.\n"
                "- \"open_aelin\": optionally takes a `route` string (e.g. \"/\") to bring the Aelin desktop app to front.\n\n"
                "Any other action will return "
                "\"unsupported device action: allowed actions are 'status', 'open_url', 'open_aelin'\".\n"
                "If you see errors like \"invalid_url_scheme\" or \"desktop_open_url_failed:...\", fix the URL "
                "or wait for the desktop plugin to become available before retrying."
            )

        if name in {"web_search", "attachment_search", "google_workspace", "device", "screen_get"}:
            if name == "device":
                tools.append(_make_device_tool(desc))
            else:
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
        "Answer the user directly in the same language as the query.\n\n"
        "Tool usage guidelines:\n"
        "- Be deliberate when calling tools; only call a tool when it is clearly helpful to the user.\n"
        "- Prefer to call a tool once with well-structured arguments instead of many times with incomplete ones.\n\n"
        "Web search tool (`web_search`):\n"
        "- Required arguments: `action` (\"search\" or \"search_and_fetch\") and a non-empty `query` string.\n"
        "- Optional arguments: `max_results` in [1, 15], `fetch_top_k` in [0, 6] and <= `max_results`.\n"
        "- If you ever see an error like \"missing query\", you MUST include a non-empty `query` field the next time.\n\n"
        "Device tool (`device` for desktop actions):\n"
        "- Allowed actions: \"status\", \"open_url\", \"open_aelin\". Do NOT invent new actions.\n"
        "- Use `status` to understand which desktop capabilities are available.\n"
        "- For `open_url`, always provide a valid http(s) URL in `url` and avoid dangerous schemes like `file://`.\n"
        "- Only call `device` when you genuinely need desktop interaction; otherwise prefer pure chat or web tools.\n\n"
        "Filesystem tools (DeepAgents built-ins such as `ls`, `read_file`, `write_file`, `edit_file`, `grep`, `glob`):\n"
        "- When the user explicitly asks you to inspect or summarize `/memory/AGENTS.md`, you SHOULD use `ls` and "
        "`read_file` to open that file instead of guessing its contents.\n"
        "- Prefer to keep writes minimal; for memory inspection tasks, `read_file` is usually enough.\n"
        "- Treat `/memory/AGENTS.md` as the authoritative long-term memory summary for this workspace."
    )

    skills_root = skills_root or (Path(__file__).resolve().parent.parent.parent / "deepagents_skills")
    skill_files: dict[str, str] = {}
    # DeepAgents SkillsMiddleware 期望 sources 是“技能根目录”，其下每个子目录
    # 才是单个 skill（包含 SKILL.md）。因此我们在虚拟文件系统中统一挂载到
    # `/skills/aelin/<skill-name>/SKILL.md` 之类的路径，而不是早期版本那样直接
    # 使用 `/<skill-name>/README.md`。
    skill_sources: list[str] = []
    aelin_skills_root_path = "/skills/aelin/"
    if skills_root.is_dir():
        # DeepAgents skills 目前只挂载仍然有效的技能目录。与 plane/PinchTab
        # 强相关的技能（plane_browser / plane_goose / plane_cli_anything 等）
        # 已在本分支下线，只作为历史文档保存在 docs/archive 中，因此这里显式
        # 跳过这些目录，即便它们作为空目录仍然存在于仓库中。
        deprecated_skill_dirs = {
            "plane_browser",
            "plane_cli_anything",
            "plane_goose",
        }
        has_any_skill = False
        for subdir in skills_root.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name in deprecated_skill_dirs:
                continue
            # 物理目录名允许使用下划线，但按照 Agent Skills 规范，skill name /
            # 虚拟目录名只能包含小写字母、数字和连字符，因此这里做一次规范化。
            raw_dir_name = subdir.name
            skill_dir_name = raw_dir_name.replace("_", "-")
            virtual_dir = f"{aelin_skills_root_path}{skill_dir_name}/"
            md_files = list(subdir.rglob("*.md"))
            if not md_files:
                continue
            has_any_skill = True
            for file_path in md_files:
                try:
                    text = file_path.read_text(encoding="utf-8")
                except Exception:
                    continue
                virtual_path = f"{virtual_dir}{file_path.name}"
                skill_files[virtual_path] = text
        if has_any_skill:
            # SkillsMiddleware 会在 `/skills/aelin/` 之下查找子目录并解析其中的
            # `SKILL.md` 文件，因此 sources 只需包含这一层根路径即可。
            skill_sources.append(aelin_skills_root_path)

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
