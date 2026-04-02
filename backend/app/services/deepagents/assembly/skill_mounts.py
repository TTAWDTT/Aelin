from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillMountSnapshot:
    skill_sources: list[str]
    mounted_skills: list[str]


_SKILL_MOUNT_CACHE_LOCK = threading.Lock()
_SKILL_MOUNT_CACHE: dict[tuple[str, str], SkillMountSnapshot] = {}


def _build_skill_mount_snapshot(skills_root: Path, extra_dir: str) -> SkillMountSnapshot:
    skill_sources: list[str] = []
    mounted_skills: list[str] = []

    def _mount_skills_from_root(root: Path, virtual_root: str) -> None:
        nonlocal skill_sources, mounted_skills

        if not root.is_dir():
            return

        has_any = False
        for subdir in root.iterdir():
            if not subdir.is_dir():
                continue
            skill_md = subdir / "SKILL.md"
            if not skill_md.is_file():
                continue

            has_any = True
            mounted_skills.append(f"{virtual_root}{subdir.name}/")

        if has_any and virtual_root not in skill_sources:
            skill_sources.append(virtual_root)

    _mount_skills_from_root(skills_root, "/skills/aelin/")
    if extra_dir:
        _mount_skills_from_root(Path(extra_dir), "/skills/external/")

    return SkillMountSnapshot(
        skill_sources=list(skill_sources),
        mounted_skills=list(mounted_skills),
    )


def get_skill_mount_snapshot(skills_root: Path, extra_dir: str) -> SkillMountSnapshot:
    key = (str(skills_root), str(Path(extra_dir)) if extra_dir else "")
    with _SKILL_MOUNT_CACHE_LOCK:
        snapshot = _SKILL_MOUNT_CACHE.get(key)
        if snapshot is None:
            snapshot = _build_skill_mount_snapshot(skills_root, extra_dir)
            _SKILL_MOUNT_CACHE[key] = snapshot
        return snapshot
