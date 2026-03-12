from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SKILLS_DIR = (_BACKEND_DIR / "skills").resolve()


@dataclass(frozen=True)
class LoadedSkill:
    name: str
    slug: str
    version: str
    applies_to_tools: tuple[str, ...]
    trigger_keywords: tuple[str, ...]
    body: str
    path: Path


def _clean_text(raw: str) -> str:
    return "\n".join(str(raw or "").replace("\r\n", "\n").split("\n")).strip()


def _split_csv(raw: str) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for item in str(raw or "").split(","):
        clean = " ".join(item.strip().split())
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return tuple(out)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    normalized = str(text or "").replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, _clean_text(normalized)
    end = normalized.find("\n---\n", 4)
    if end == -1:
        return {}, _clean_text(normalized)
    raw_meta = normalized[4:end]
    body = normalized[end + 5 :]
    meta: dict[str, str] = {}
    for line in raw_meta.split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[str(key).strip().lower()] = str(value).strip()
    return meta, _clean_text(body)


def _matches_tools(skill: LoadedSkill, tool_names: list[str] | None) -> bool:
    applies = {item.lower() for item in skill.applies_to_tools}
    if not applies:
        return True
    active = {str(item or "").strip().lower() for item in list(tool_names or []) if str(item or "").strip()}
    return bool(applies & active)


def _matches_query(skill: LoadedSkill, query: str) -> bool:
    keywords = [item.lower() for item in skill.trigger_keywords]
    if not keywords:
        return True
    hay = str(query or "").strip().lower()
    if not hay:
        return False
    return any(token in hay for token in keywords)


def _format_skill_prompt(skill: LoadedSkill) -> str:
    applies = ",".join(skill.applies_to_tools)
    keywords = ",".join(skill.trigger_keywords)
    header_lines = [
        "[AELIN SKILL]",
        f"name={skill.name}",
        f"slug={skill.slug}",
    ]
    if skill.version:
        header_lines.append(f"version={skill.version}")
    if applies:
        header_lines.append(f"applies_to_tools={applies}")
    if keywords:
        header_lines.append(f"trigger_keywords={keywords}")
    return "\n".join([*header_lines, "", skill.body]).strip()


@lru_cache(maxsize=1)
def _load_all_skills() -> tuple[LoadedSkill, ...]:
    skills: list[LoadedSkill] = []
    if not _SKILLS_DIR.is_dir():
        return tuple()
    for path in sorted(_SKILLS_DIR.glob("*/SKILL.md")):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        meta, body = _parse_frontmatter(raw)
        slug = str(meta.get("slug") or path.parent.name).strip() or path.parent.name
        name = str(meta.get("name") or slug).strip() or slug
        version = str(meta.get("version") or "").strip()
        applies = _split_csv(meta.get("applies_to_tools") or "")
        triggers = _split_csv(meta.get("trigger_keywords") or "")
        if not body:
            continue
        skills.append(
            LoadedSkill(
                name=name,
                slug=slug,
                version=version,
                applies_to_tools=applies,
                trigger_keywords=triggers,
                body=body,
                path=path,
            )
        )
    return tuple(skills)


def get_skill_bodies_for_query_and_tools(query: str, tool_names: list[str] | None = None) -> list[str]:
    out: list[str] = []
    for skill in _load_all_skills():
        if not _matches_tools(skill, tool_names):
            continue
        if not _matches_query(skill, query):
            continue
        out.append(skill.body)
    return out


def get_skill_prompts_for_query_and_tools(query: str, tool_names: list[str] | None = None) -> list[str]:
    prompts: list[str] = []
    for skill in _load_all_skills():
        if not _matches_tools(skill, tool_names):
            continue
        if not _matches_query(skill, query):
            continue
        prompts.append(_format_skill_prompt(skill))
    return prompts
