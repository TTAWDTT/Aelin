from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas import AgentConfigOut
from app.services.deepagents.deepagents_graph import run_deepagents_loop
from app.services.deepagents.tool_runtime import ToolCallLimiter, build_tool_runtime_context
from app.services.foundation.encryption import decrypt_optional
from app.services.foundation.llm import LLMService

DEFAULT_JSON = ROOT / "docs" / "deepagents_skill_matrix_report.json"
DEFAULT_MD = ROOT / "docs" / "deepagents_skill_matrix_report.md"


@dataclass(frozen=True)
class EnvSmoke:
    command: str
    expect_markers: tuple[str, ...] = ()
    blocked_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillProbe:
    skill: str
    prompt: str
    expected_markers: tuple[str, ...]
    env_smoke: EnvSmoke | None = None


@dataclass
class ProbeResult:
    skill: str
    ok: bool
    answer: str
    expected_markers: list[str]
    markers_hit: list[str]
    tool_runs: list[dict[str, Any]]
    capability_summary: str
    error: str
    env_status: str = "not_checked"
    env_command: str = ""
    env_excerpt: str = ""
    env_error: str = ""


PROBES: list[SkillProbe] = [
    SkillProbe(
        skill="anthropic-canvas-design",
        prompt=(
            "Please read /skills/aelin/anthropic-canvas-design/SKILL.md and answer in English: "
            "what are the two high-level steps in its workflow?"
        ),
        expected_markers=("design philosophy creation", "canvas"),
    ),
    SkillProbe(
        skill="anthropic-docx",
        prompt=(
            "Please read /skills/aelin/anthropic-docx/SKILL.md and answer with the exact command "
            "it shows for converting a legacy .doc file to .docx."
        ),
        expected_markers=("soffice.py", "--convert-to docx"),
        env_smoke=EnvSmoke(
            command="python backend/deepagents_skills/anthropic-docx/scripts/accept_changes.py --help",
            expect_markers=("usage",),
            blocked_markers=("module", "no module named", "traceback"),
        ),
    ),
    SkillProbe(
        skill="anthropic-pdf",
        prompt=(
            "Please read /skills/aelin/anthropic-pdf/SKILL.md and answer in Chinese: "
            "which Python library does it recommend for extracting tables from PDFs?"
        ),
        expected_markers=("pdfplumber",),
        env_smoke=EnvSmoke(
            command="python backend/deepagents_skills/anthropic-pdf/scripts/extract_form_structure.py --help",
            expect_markers=("usage",),
            blocked_markers=("no module named", "traceback", "module"),
        ),
    ),
    SkillProbe(
        skill="anthropic-pptx",
        prompt=(
            "Please read /skills/aelin/anthropic-pptx/SKILL.md and answer with the exact command "
            "it recommends for text extraction from a presentation."
        ),
        expected_markers=("markitdown", "presentation.pptx"),
        env_smoke=EnvSmoke(
            command="python backend/deepagents_skills/anthropic-pptx/scripts/thumbnail.py --help",
            expect_markers=("usage",),
            blocked_markers=("no module named", "traceback", "module"),
        ),
    ),
    SkillProbe(
        skill="anthropic-skill-creator",
        prompt=(
            "Please read /skills/aelin/anthropic-skill-creator/SKILL.md and answer in English: "
            "after writing a draft skill, what evaluation-related phase and what rewrite-related phase does it emphasize?"
        ),
        expected_markers=("evaluation", "rewrite"),
    ),
    SkillProbe(
        skill="anthropic-xlsx",
        prompt=(
            "Please read /skills/aelin/anthropic-xlsx/SKILL.md and answer in English: "
            "what is the required font rule and what is the formula-error rule for Excel outputs?"
        ),
        expected_markers=("zero formula errors", "professional font"),
        env_smoke=EnvSmoke(
            command="python backend/deepagents_skills/anthropic-xlsx/scripts/recalc.py",
            expect_markers=("usage",),
            blocked_markers=("no module named", "traceback", "module"),
        ),
    ),
    SkillProbe(
        skill="callstack-github",
        prompt=(
            "Please read /skills/aelin/callstack-github/SKILL.md and answer with the exact gh CLI "
            "command template it gives for squash-merging a PR."
        ),
        expected_markers=("gh pr merge", "--squash"),
        env_smoke=EnvSmoke(
            command="gh --version",
            expect_markers=("gh version",),
        ),
    ),
    SkillProbe(
        skill="chrome-cdp",
        prompt=(
            "Please read /skills/aelin/chrome-cdp/SKILL.md and answer with the exact command it "
            "recommends for listing open pages."
        ),
        expected_markers=("scripts/cdp.mjs list",),
        env_smoke=EnvSmoke(
            command="node backend/deepagents_skills/chrome-cdp/scripts/cdp.mjs list",
            blocked_markers=("No DevToolsActivePort found", "Enable remote debugging"),
        ),
    ),
    SkillProbe(
        skill="codebase-documenter",
        prompt=(
            "Please read /skills/aelin/codebase-documenter/SKILL.md and answer in English: "
            "name two markdown files it says should appear under docs/ output."
        ),
        expected_markers=("architecture.md", "development.md"),
    ),
    SkillProbe(
        skill="exploratory-data-analysis",
        prompt=(
            "Please read /skills/aelin/exploratory-data-analysis/SKILL.md and answer in English: "
            "what example file extension appears in the analysis flow example?"
        ),
        expected_markers=(".fastq",),
    ),
    SkillProbe(
        skill="file_tools",
        prompt=(
            "请读取 /skills/aelin/file-tools/SKILL.md 并只回答一句中文："
            "当用户说“总结这个 PDF”时，推荐第一步调用什么？"
        ),
        expected_markers=("attachment_search",),
    ),
    SkillProbe(
        skill="firecrawl-browser",
        prompt=(
            "Please read /skills/aelin/firecrawl-browser/SKILL.md and answer in English: "
            "what must happen before using interact?"
        ),
        expected_markers=("scrape", "first"),
        env_smoke=EnvSmoke(
            command="firecrawl interact --help",
            expect_markers=("interact",),
            blocked_markers=("not recognized", "not found"),
        ),
    ),
    SkillProbe(
        skill="firecrawl-cli",
        prompt=(
            "Please read /skills/aelin/firecrawl-cli/SKILL.md and answer in English: "
            "list the five workflow escalation steps in order."
        ),
        expected_markers=("search", "scrape", "map", "crawl", "interact"),
        env_smoke=EnvSmoke(
            command="firecrawl --help",
            expect_markers=("firecrawl",),
            blocked_markers=("not recognized", "not found"),
        ),
    ),
    SkillProbe(
        skill="google_workspace",
        prompt=(
            "请读取 /skills/aelin/google-workspace/SKILL.md 并回答中文："
            "在尝试写操作前，应该先调用哪个 action 检查登录和 scope？"
        ),
        expected_markers=("auth_status",),
        env_smoke=EnvSmoke(
            command="gws auth status",
            expect_markers=("authenticated", "config", "gws"),
            blocked_markers=("timeout", "not recognized", "not found"),
        ),
    ),
    SkillProbe(
        skill="kaizen",
        prompt=(
            "Please read /skills/aelin/kaizen/SKILL.md and answer in English: "
            "what are the labels for Iteration 1, Iteration 2, and Iteration 3 in the calculateTotal example?"
        ),
        expected_markers=("make it work", "make it clear", "make it robust"),
    ),
    SkillProbe(
        skill="literature-review",
        prompt=(
            "Please read /skills/aelin/literature-review/SKILL.md and answer with the python command example "
            "it gives for generating a schematic figure."
        ),
        expected_markers=("generate_schematic.py", "figures/output.png"),
    ),
    SkillProbe(
        skill="paper-slide-deck",
        prompt=(
            "请读取 /skills/aelin/paper-slide-deck/SKILL.md 并回答中文："
            "Step 5 提供给用户的两种图像生成方式是什么？"
        ),
        expected_markers=("gemini api", "gemini web"),
        env_smoke=EnvSmoke(
            command="python backend/deepagents_skills/paper-slide-deck/scripts/generate-slides.py --help",
            expect_markers=("usage", "slide_deck_dir"),
            blocked_markers=("no module named", "traceback", "module"),
        ),
    ),
    SkillProbe(
        skill="project-bootstrapper",
        prompt=(
            "Please read /skills/aelin/project-bootstrapper/SKILL.md and answer in English: "
            "name three standard directories it says should be set up for project structure."
        ),
        expected_markers=("src/", "tests/", "docs/"),
    ),
    SkillProbe(
        skill="scientific-critical-thinking",
        prompt=(
            "Please read /skills/aelin/scientific-critical-thinking/SKILL.md and answer in English: "
            "which two evidence-quality frameworks does it explicitly mention?"
        ),
        expected_markers=("grade", "cochrane"),
    ),
    SkillProbe(
        skill="scientific-writing",
        prompt=(
            "Please read /skills/aelin/scientific-writing/SKILL.md and answer in English: "
            "what visual element does it say every scientific paper must include, and what writing format does it forbid in final manuscripts?"
        ),
        expected_markers=("graphical abstract", "bullet points"),
    ),
    SkillProbe(
        skill="solid",
        prompt=(
            "Please read /skills/aelin/solid/SKILL.md and answer in English: "
            "what are the three mandatory TDD phases it lists?"
        ),
        expected_markers=("red", "green", "refactor"),
    ),
    SkillProbe(
        skill="trailofbits-modern-python",
        prompt=(
            "Please read /skills/aelin/trailofbits-modern-python/SKILL.md and answer in English: "
            "which dependency command does it say to avoid, and which command should be used instead?"
        ),
        expected_markers=("uv pip install", "uv add"),
    ),
    SkillProbe(
        skill="translation",
        prompt=(
            "Please read /skills/aelin/translation/SKILL.md and answer in Chinese: "
            "the phrase 'Keep structure but sound natural' should use which mode?"
        ),
        expected_markers=("natural",),
    ),
]


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _find_db_row(user_id: int) -> tuple[Path, tuple[Any, ...]]:
    candidates = [
        ROOT / "aelin.db",
        ROOT / "mercurydesk.db",
    ]
    query = (
        "SELECT user_id, provider, base_url, model, temperature, verify_ssl, api_key, web_search_proxy_url "
        "FROM agent_configs WHERE user_id = ? LIMIT 1"
    )
    for db_path in candidates:
        if not db_path.is_file():
            continue
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute(query, (user_id,))
            row = cur.fetchone()
        except Exception:
            row = None
        finally:
            conn.close()
        if row:
            return db_path, row
    raise RuntimeError(f"no agent config found for user_id={user_id}")


def _build_service(user_id: int) -> tuple[LLMService, str]:
    db_path, row = _find_db_row(user_id)
    _, provider, base_url, model, temperature, verify_ssl, api_key_enc, web_search_proxy_url = row
    api_key = decrypt_optional(api_key_enc)
    if not api_key:
        raise RuntimeError(f"api key decrypt failed for user_id={user_id} from {db_path}")
    config = AgentConfigOut(
        provider=(provider or "openai"),
        base_url=(base_url or ""),
        model=(model or ""),
        temperature=float(temperature or 0.2),
        verify_ssl=bool(verify_ssl),
        has_api_key=True,
        web_search_proxy_url=str(web_search_proxy_url or ""),
    )
    service = LLMService(config, api_key)
    if not service.is_configured():
        raise RuntimeError(f"llm service not configured for user_id={user_id}")
    return service, str(provider or "openai")


def _run_env_smoke(smoke: EnvSmoke) -> tuple[str, str, str]:
    try:
        completed = subprocess.run(
            smoke.command,
            cwd=str(ROOT.parent),
            capture_output=True,
            text=True,
            timeout=45,
            shell=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return "timeout", "", "env smoke timed out after 45s"
    except Exception as exc:  # noqa: BLE001
        return "error", "", f"{type(exc).__name__}: {exc}"

    combined = "\n".join(
        part.strip() for part in [completed.stdout.strip(), completed.stderr.strip()] if part.strip()
    )
    normalized = _normalize(combined)
    if any(marker.lower() in normalized for marker in smoke.blocked_markers):
        return "blocked", combined[:1200], ""
    if smoke.expect_markers and not all(marker.lower() in normalized for marker in smoke.expect_markers):
        status = "warning" if completed.returncode == 0 else "failed"
        return status, combined[:1200], ""
    status = "passed" if completed.returncode == 0 else "warning"
    return status, combined[:1200], ""


def _run_skill_probe(
    probe: SkillProbe,
    *,
    service: LLMService,
    provider: str,
    user_id: int,
    workspace: str,
    max_tool_calls: int,
) -> ProbeResult:
    context = build_tool_runtime_context(
        db=None,
        user_id=user_id,
        workspace=workspace,
    )
    result = run_deepagents_loop(
        service=service,
        provider=provider,
        context=context,
        limiter=ToolCallLimiter(
            max_tool_calls=max_tool_calls,
            max_write_calls=2,
            allow_write_tools=False,
        ),
        query=probe.prompt,
        memory_text="",
        history_turns=[],
        images=[],
    )
    answer = str(result.answer or "")
    normalized_answer = _normalize(answer)
    markers_hit = [marker for marker in probe.expected_markers if marker.lower() in normalized_answer]
    ok = bool(result.ok) and len(markers_hit) == len(probe.expected_markers)

    probe_result = ProbeResult(
        skill=probe.skill,
        ok=ok,
        answer=answer,
        expected_markers=list(probe.expected_markers),
        markers_hit=markers_hit,
        tool_runs=[
            {
                "name": run.name,
                "status": run.status,
                "args": run.args,
                "result": run.result,
                "error": run.error,
                "latency_ms": run.latency_ms,
            }
            for run in result.tool_runs
        ],
        capability_summary=result.capability_summary,
        error=result.error,
    )
    if probe.env_smoke is not None:
        env_status, env_excerpt, env_error = _run_env_smoke(probe.env_smoke)
        probe_result.env_status = env_status
        probe_result.env_command = probe.env_smoke.command
        probe_result.env_excerpt = env_excerpt
        probe_result.env_error = env_error
    return probe_result


def _to_markdown(results: list[ProbeResult]) -> str:
    lines = [
        "# DeepAgents Skill Matrix Report",
        "",
        f"Total skills tested: {len(results)}",
        f"Prompt-chain passes: {sum(1 for item in results if item.ok)}",
        f"Env smokes passed: {sum(1 for item in results if item.env_status == 'passed')}",
        f"Env smokes blocked: {sum(1 for item in results if item.env_status == 'blocked')}",
        "",
        "| Skill | Prompt Chain | Env Smoke | Tool Calls |",
        "| --- | --- | --- | --- |",
    ]
    for item in results:
        prompt_status = "PASS" if item.ok else "FAIL"
        env_status = item.env_status
        lines.append(
            f"| {item.skill} | {prompt_status} | {env_status} | {len(item.tool_runs)} |"
        )
    lines.append("")
    for item in results:
        lines.extend(
            [
                f"## {item.skill}",
                "",
                f"- Prompt chain: {'PASS' if item.ok else 'FAIL'}",
                f"- Capability summary: `{item.capability_summary}`",
                f"- Expected markers: `{', '.join(item.expected_markers)}`",
                f"- Markers hit: `{', '.join(item.markers_hit)}`",
                f"- Env smoke: `{item.env_status}`",
            ]
        )
        if item.env_command:
            lines.append(f"- Env command: `{item.env_command}`")
        if item.error:
            lines.append(f"- Chain error: `{item.error}`")
        if item.env_error:
            lines.append(f"- Env error: `{item.env_error}`")
        lines.extend(
            [
                "",
                "### Answer",
                "",
                "```text",
                item.answer.strip() or "<empty>",
                "```",
                "",
            ]
        )
        if item.tool_runs:
            lines.extend(["### Tool Runs", "", "```json", json.dumps(item.tool_runs, ensure_ascii=False, indent=2), "```", ""])
        if item.env_excerpt:
            lines.extend(["### Env Output", "", "```text", item.env_excerpt, "```", ""])
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real DeepAgents skill-chain probes for all mounted skills.")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--workspace", default="default")
    parser.add_argument("--max-tool-calls", type=int, default=8)
    parser.add_argument("--output-json", default=str(DEFAULT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_MD))
    args = parser.parse_args()

    service, provider = _build_service(args.user_id)
    results = [
        _run_skill_probe(
            probe,
            service=service,
            provider=provider,
            user_id=args.user_id,
            workspace=args.workspace,
            max_tool_calls=args.max_tool_calls,
        )
        for probe in PROBES
    ]

    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(_to_markdown(results), encoding="utf-8")

    summary = {
        "json_report": str(json_path),
        "md_report": str(md_path),
        "total": len(results),
        "prompt_chain_passes": sum(1 for item in results if item.ok),
        "env_passes": sum(1 for item in results if item.env_status == "passed"),
        "env_blocked": sum(1 for item in results if item.env_status == "blocked"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
