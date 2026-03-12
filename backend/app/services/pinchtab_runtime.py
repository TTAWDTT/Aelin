from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from app.settings import settings


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_DIR = _BACKEND_DIR.parent
_PINCHTAB_EXE = "pinchtab.exe" if sys.platform.startswith("win") else "pinchtab"


def _resolve_backend_path(raw: str, *, default: str) -> Path:
    text = str(raw or "").strip() or default
    path = Path(text)
    if path.is_absolute():
        return path
    return (_BACKEND_DIR / path).resolve()


class PinchTabRuntime:
    """
    Resolve PinchTab runtime paths relative to the Aelin project layout.

    PinchTab should live alongside the packaged/runtime assets of Aelin rather
    than inside user-level global directories.
    """

    def configured_executable_path(self) -> Path:
        return _resolve_backend_path(settings.pinchtab_executable_path, default=f"./bin/{_PINCHTAB_EXE}")

    def source_dir(self) -> Path:
        return _resolve_backend_path(settings.pinchtab_source_dir, default="./.pinchtab")

    def data_dir(self) -> Path:
        return _resolve_backend_path(settings.pinchtab_data_dir, default="../data/pinchtab")

    def browser_data_dir(self) -> Path:
        return (self.data_dir() / "browser").resolve()

    def profiles_dir(self) -> Path:
        return (self.data_dir() / "profiles").resolve()

    def logs_dir(self) -> Path:
        return (self.data_dir() / "logs").resolve()

    def config_path(self) -> Path:
        return (self.data_dir() / "config.json").resolve()

    def log_path(self) -> Path:
        return (self.logs_dir() / "pinchtab.log").resolve()

    def pid_path(self) -> Path:
        return (self.data_dir() / "pinchtab.pid").resolve()

    def fallback_executable_candidates(self) -> list[Path]:
        candidates = [
            (_BACKEND_DIR / "pinchtab_probe_2" / _PINCHTAB_EXE).resolve(),
            (self.source_dir() / _PINCHTAB_EXE).resolve(),
        ]
        out: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
        return out

    def executable_candidates(self) -> list[Path]:
        out: list[Path] = []
        seen: set[str] = set()
        for path in [self.configured_executable_path(), *self.fallback_executable_candidates()]:
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
        return out

    def resolved_executable_path(self) -> Path | None:
        for path in self.executable_candidates():
            if path.is_file():
                return path
        return None

    def status(self) -> dict[str, Any]:
        configured_executable = self.configured_executable_path()
        resolved_executable = self.resolved_executable_path()
        source_dir = self.source_dir()
        data_dir = self.data_dir()
        browser_data_dir = self.browser_data_dir()
        profiles_dir = self.profiles_dir()
        logs_dir = self.logs_dir()
        config_path = self.config_path()
        log_path = self.log_path()
        pid_path = self.pid_path()
        return {
            "configured_executable_path": str(configured_executable),
            "resolved_executable_path": str(resolved_executable) if resolved_executable else "",
            "source_dir": str(source_dir),
            "data_dir": str(data_dir),
            "browser_data_dir": str(browser_data_dir),
            "profiles_dir": str(profiles_dir),
            "logs_dir": str(logs_dir),
            "config_path": str(config_path),
            "log_path": str(log_path),
            "pid_path": str(pid_path),
            "source_dir_exists": source_dir.is_dir(),
            "data_dir_exists": data_dir.is_dir(),
            "browser_data_dir_exists": browser_data_dir.is_dir(),
            "profiles_dir_exists": profiles_dir.is_dir(),
            "logs_dir_exists": logs_dir.is_dir(),
            "config_path_exists": config_path.is_file(),
            "log_path_exists": log_path.is_file(),
            "pid_path_exists": pid_path.is_file(),
            "executable_exists": resolved_executable is not None,
            "candidate_executable_paths": [str(path) for path in self.executable_candidates()],
            "project_dir": str(_PROJECT_DIR),
            "backend_dir": str(_BACKEND_DIR),
        }


_pinchtab_runtime: PinchTabRuntime | None = None


def get_pinchtab_runtime() -> PinchTabRuntime:
    global _pinchtab_runtime
    if _pinchtab_runtime is None:
        _pinchtab_runtime = PinchTabRuntime()
    return _pinchtab_runtime
