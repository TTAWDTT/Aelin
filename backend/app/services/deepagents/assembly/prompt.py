from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.services.deepagents.delivery_paths import get_delivery_paths


_AELIN_TIMEZONE = "Asia/Shanghai"


def _current_date_context() -> str:
    try:
        local_now = datetime.now(ZoneInfo(_AELIN_TIMEZONE))
    except Exception:
        local_now = datetime.now(timezone.utc)
    return (
        f"Current date: {local_now.date().isoformat()}.\n"
        f"Current timezone: {_AELIN_TIMEZONE}.\n"
        f"Current local datetime: {local_now.isoformat(timespec='seconds')}.\n"
        f"Today in {_AELIN_TIMEZONE}: {local_now.strftime('%Y-%m-%d')}.\n"
        "Interpret relative date and time references using the current local datetime above unless a tool result from this run proves otherwise.\n"
        "Do not drift to another year or another date just because retrieved content mentions one."
    )


def tool_description(name: str) -> str:
    if name == "memory_search":
        return (
            "Search long-term memory without injecting the entire memory corpus into the prompt.\n"
            "Arguments: query=<non-empty string>, top_k=1..20, kinds?<string[]>.\n"
            "Use before opening /memory/*.md files when you need past preferences, facts, projects, or recent context.\n"
            "Prefer one focused query over repeated vague retries."
        )
    if name == "web_search":
        return (
            "Search the public web.\n"
            "Arguments: action=('search'|'search_and_fetch'), query=<non-empty string>, "
            "max_results=1..15, fetch_top_k=0..6.\n"
            "Never call web_search with an empty query. Do not repeat materially identical queries in the same run. "
            "If one search already returned enough evidence, stop searching and answer."
        )
    if name == "attachment_search":
        return (
            "Search uploaded attachments for relevant chunks.\n"
            "Arguments: query=<non-empty string>, attachment_ids?<int[]>, top_k=1..20, "
            "mode=('keyword'|'hybrid').\n"
            "attachment_ids is optional when this run already provides available_attachment_ids in /runtime/capabilities.json; "
            "the runtime will use those scoped ids automatically.\n"
            "Always provide a concrete non-empty query that reflects what information you need from the files "
            "(for example 'project codename deadline deliverables').\n"
            "Do not repeat the same query against the same attachments. If there are no useful hits, say so and stop."
        )
    if name == "google_workspace":
        return (
            "Access Google Workspace via local gws CLI.\n"
            "Use action to select runtime/auth/gmail/drive/calendar/docs operations.\n"
            "Before calling, ensure action-specific required fields are present. Never retry the same write action blindly."
        )
    if name == "device":
        return (
            "Desktop actions and status.\n"
            "Allowed actions: 'status', 'open_url', 'open_aelin'.\n"
            "Use device only when the user explicitly asks for a desktop action such as opening a page or switching the Aelin app.\n"
            "For open_url pass a valid http(s) URL. Do not repeat the same desktop action if it already failed once."
        )
    if name == "screen_get":
        return (
            "Capture a desktop screenshot for visual inspection.\n"
            "Only use when visual evidence is required. Avoid repeated screenshots with the same arguments."
        )
    if name == "execute":
        return (
            "Execute a non-interactive shell command on the local desktop runtime.\n"
            "Arguments: command=<non-empty string>, shell?=('cmd'|'powershell'), cwd?<allowed directory>, timeout_ms=1000..120000.\n"
            "Use for coding, document generation, rendering, or inspection tasks like running tests, listing files, or checking git status.\n"
            "When cwd is omitted, the runtime uses the mapped DeepAgents workspace directory for this conversation.\n"
            "Commands run in the local desktop shell. On Windows, prefer PowerShell or cmd syntax rather than Unix-only syntax.\n"
            "When targeting a specific directory, prefer passing cwd instead of chaining cd, and then write outputs using relative paths inside that cwd so the runtime can collect artifacts.\n"
            "If cwd is already provided, do not prepend cd to the command.\n"
            "On Windows, prefer shell='powershell' when using Set-Content, Out-File, New-Item, Get-Content, Test-Path, or other PowerShell cmdlets, and pass the PowerShell script body directly rather than prefixing it with powershell -Command.\n"
            "Do not use Unix-only constructs like mkdir -p.\n"
            "Avoid interactive commands, long-running dev servers, or commands that wait for user input."
        )
    if name == "present_files":
        return (
            "Present finished user-facing files in the chat UI.\n"
            "Arguments: filepaths=<list of file paths>.\n"
            "Only present final deliverables that already exist under /outputs or the mapped outputs directory.\n"
            "Call this after generating the final files so the user receives clickable preview/download cards."
        )
    return name


def build_system_prompt(
    tool_names: list[str],
    *,
    user_id: int,
    workspace: str,
) -> str:
    available = {str(name or "").strip() for name in tool_names if str(name or "").strip()}
    delivery_paths = get_delivery_paths(workspace=workspace, user_id=user_id)
    workspace_virtual = delivery_paths.workspace_virtual_path
    outputs_virtual = delivery_paths.outputs_virtual_path
    workspace_local = delivery_paths.workspace_dir.as_posix()
    outputs_local = delivery_paths.outputs_dir.as_posix()
    tool_specific_rules: list[str] = []
    if "memory_search" in available:
        tool_specific_rules.append(
            "- memory_search: use it before opening /memory/*.md files when you need long-term memory; prefer a specific query and optional kinds filter."
        )
    if "web_search" in available:
        tool_specific_rules.append(
            "- web_search: always provide a non-empty query; avoid repeated near-duplicate queries; stop once you have enough evidence."
        )
    if "attachment_search" in available:
        tool_specific_rules.append(
            "- attachment_search: when the user asks about uploaded files, call attachment_search with a concrete non-empty query describing the requested facts. "
            "If this run already scopes uploaded attachments for you, attachment_ids may be omitted and the runtime will apply the scoped ids automatically. "
            "Do not claim an attachment is unavailable unless attachment_search actually failed in this run."
        )
    if "google_workspace" in available:
        tool_specific_rules.append(
            "- google_workspace: choose a concrete action and include all required fields before calling; never blindly retry writes."
        )
    if "device" in available:
        tool_specific_rules.append(
            "- device: only use status/open_url/open_aelin when the user explicitly asks for desktop or browser navigation; open_url requires a valid http(s) URL."
        )
    if "screen_get" in available:
        tool_specific_rules.append(
            "- screen_get: capture only when visual evidence is necessary; avoid repeated screenshots with the same arguments."
        )
    if "execute" in available:
        tool_specific_rules.append(
            f"- execute: use it for local generation, rendering, conversion, and testing. Omit cwd to use the mapped workspace directory `{workspace_local}` by default. You may also pass cwd as `{workspace_virtual}`, `{outputs_virtual}`, `{workspace_local}`, or `{outputs_local}`. On Windows prefer PowerShell/cmd syntax, do not prepend cd when cwd is already provided, use shell='powershell' for PowerShell cmdlets, and avoid Unix-only constructs like mkdir -p."
        )
    if "present_files" in available:
        tool_specific_rules.append(
            f"- present_files: final deliverables must be placed under `{outputs_virtual}` (real local path `{outputs_local}`), then call `present_files` with those file paths so the UI can render cards. Do not call it for temporary or intermediate files."
        )

    parts = [
        "You are Aelin running on DeepAgents.\n"
        "Reply in the same language as the user.\n"
        "Use tools only when they materially help.\n"
        "Prefer one correct tool call over repeated partial attempts.\n"
        "Before calling any tool, first form a complete and valid argument set.\n"
        "If a tool call is rejected for missing or invalid arguments, correct the arguments once instead of retrying blindly.\n"
        "Do not repeat materially identical tool calls in the same run unless new evidence changes the request.\n"
        "If two recent tool attempts failed or produced no new information, stop using tools and answer from the current evidence.\n"
        "When a tool is unavailable, unauthorized, times out, or returns no useful information, say that clearly and move on.\n"
        f"Real filesystem contract for this run:\n"
        f"- `{workspace_virtual}` is the on-disk working directory for source files and intermediate assets. It maps to `{workspace_local}`.\n"
        f"- `{outputs_virtual}` is the on-disk final-deliverables directory. It maps to `{outputs_local}`.\n"
        "- Files written under those two virtual roots are real local files, not just in-memory thread state.\n"
        "- Final user-facing files must end up in /outputs.\n"
        "For large generated deliverables such as posters, reports, slide decks, Word documents, PDFs, HTML/SVG artwork, or other long files, do not stuff one enormous blob into a single write_file call.\n"
        "Instead, create concise source files in /workspace, use execute to generate or render the final deliverable, save the finished files into /outputs, and then call present_files.\n"
        "If a task can be completed with normal write_file/edit_file calls under /workspace or /outputs, that is fine; but for binary formats or very large content, prefer execute plus present_files."
    ]
    if tool_specific_rules:
        parts.append("Tool-specific rules:\n" + "\n".join(tool_specific_rules))
    parts.extend(
        [
            _current_date_context(),
            "If the user asks about date-sensitive facts, keep the answer explicitly grounded to the current date context above.\n"
            "If search results contain stale dates, say that clearly instead of silently treating them as current.\n"
            "Treat /memory/AGENTS.md as the compact runtime memory projection for this run.\n"
            "Use memory_search and the other /memory/*.md files for deeper long-term memory only when needed.\n"
            "Read skills on demand from /skills/... when a matching skill is relevant.\n"
            "Never claim you searched, opened, read, or cited an external source unless the corresponding tool call succeeded in this run.\n"
            "If a required tool or skill is unavailable, say so explicitly instead of implying the action completed.",
        ]
    )
    return "\n".join(parts)
