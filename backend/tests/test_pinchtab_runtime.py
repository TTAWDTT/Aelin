from __future__ import annotations

import sys
from pathlib import Path

from app.services.pinchtab_runtime import PinchTabRuntime


_PINCHTAB_EXE = "pinchtab.exe" if sys.platform.startswith("win") else "pinchtab"


def test_pinchtab_runtime_defaults_are_aelin_relative():
    runtime = PinchTabRuntime()

    configured = runtime.configured_executable_path()
    source_dir = runtime.source_dir()
    data_dir = runtime.data_dir()

    assert configured.name == _PINCHTAB_EXE
    assert configured.parent.name == "bin"
    assert source_dir.name == ".pinchtab"
    assert data_dir.name == "pinchtab"
    assert data_dir.parent.name == "data"


def test_pinchtab_runtime_resolves_repo_local_fallback_binary(tmp_path: Path, monkeypatch):
    runtime = PinchTabRuntime()

    configured = tmp_path / "backend" / "bin" / _PINCHTAB_EXE
    fallback = tmp_path / "backend" / "pinchtab_probe_2" / _PINCHTAB_EXE
    source_dir = tmp_path / "backend" / ".pinchtab"
    data_dir = tmp_path / "data" / "pinchtab"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    fallback.write_text("binary", encoding="utf-8")

    monkeypatch.setattr(runtime, "configured_executable_path", lambda: configured)
    monkeypatch.setattr(runtime, "fallback_executable_candidates", lambda: [fallback])
    monkeypatch.setattr(runtime, "source_dir", lambda: source_dir)
    monkeypatch.setattr(runtime, "data_dir", lambda: data_dir)

    resolved = runtime.resolved_executable_path()
    status = runtime.status()

    assert resolved == fallback
    assert status["executable_exists"] is True
    assert status["resolved_executable_path"] == str(fallback)
    assert str(fallback) in status["candidate_executable_paths"]
