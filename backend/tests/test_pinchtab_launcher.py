from __future__ import annotations

import sys
from pathlib import Path

from app.services.pinchtab_launcher import PinchTabLauncher


_PINCHTAB_EXE = "pinchtab.exe" if sys.platform.startswith("win") else "pinchtab"


class _Proc:
    def __init__(self, pid: int = 4321, running: bool = True):
        self.pid = pid
        self._running = running
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._running else 0

    def terminate(self):
        self.terminated = True
        self._running = False

    def wait(self, timeout: float | None = None):
        self._running = False
        return 0

    def kill(self):
        self.killed = True
        self._running = False


class _Runtime:
    def __init__(self, root: Path):
        self._root = root

    def data_dir(self) -> Path:
        return self._root / "data"

    def browser_data_dir(self) -> Path:
        return self.data_dir() / "browser"

    def profiles_dir(self) -> Path:
        return self.data_dir() / "profiles"

    def logs_dir(self) -> Path:
        return self.data_dir() / "logs"

    def config_path(self) -> Path:
        return self.data_dir() / "config.json"

    def log_path(self) -> Path:
        return self.logs_dir() / "pinchtab.log"

    def pid_path(self) -> Path:
        return self.data_dir() / "pinchtab.pid"

    def resolved_executable_path(self) -> Path:
        exe = self._root / "bin" / _PINCHTAB_EXE
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("binary", encoding="utf-8")
        return exe

    def status(self) -> dict[str, object]:
        resolved = self.resolved_executable_path()
        return {
            "configured_executable_path": str(resolved),
            "resolved_executable_path": str(resolved),
            "source_dir": str(self._root / ".pinchtab"),
            "data_dir": str(self.data_dir()),
            "browser_data_dir": str(self.browser_data_dir()),
            "profiles_dir": str(self.profiles_dir()),
            "logs_dir": str(self.logs_dir()),
            "config_path": str(self.config_path()),
            "log_path": str(self.log_path()),
            "pid_path": str(self.pid_path()),
            "executable_exists": True,
        }


def test_launcher_writes_aelin_managed_config(tmp_path: Path, monkeypatch):
    runtime = _Runtime(tmp_path)
    launcher = PinchTabLauncher(runtime=runtime)

    class _Client:
        def runtime_status(self):
            return {"base_url": "http://127.0.0.1:9867"}

        def health(self):
            return {"ok": False, "error": "offline"}

    monkeypatch.setattr(launcher, "_client", _Client())

    launcher._ensure_dirs()
    config_path = launcher._write_config()
    payload = config_path.read_text(encoding="utf-8")

    assert config_path == runtime.config_path()
    assert '"stateDir":' in payload
    assert str(runtime.data_dir()).replace("\\", "\\\\") in payload
    assert str(runtime.profiles_dir()).replace("\\", "\\\\") in payload


def test_launcher_ensure_started_waits_until_healthy(tmp_path: Path, monkeypatch):
    runtime = _Runtime(tmp_path)
    launcher = PinchTabLauncher(runtime=runtime)
    proc = _Proc()
    health_calls: list[int] = []

    class _Client:
        def runtime_status(self):
            return {"base_url": "http://127.0.0.1:9867"}

        def health(self):
            health_calls.append(1)
            return {"ok": len(health_calls) >= 3}

    monkeypatch.setattr(launcher, "_client", _Client())

    def _fake_spawn():
        launcher._proc = proc
        launcher._write_managed_pid(proc.pid)
        return proc, ""

    monkeypatch.setattr(launcher, "_spawn_locked", _fake_spawn)
    monkeypatch.setattr("app.services.pinchtab_launcher.time.sleep", lambda _: None)

    result = launcher.ensure_started()

    assert result["ok"] is True
    assert result["status"] == "started"
    assert result["managed_pid"] == proc.pid
    assert len(health_calls) >= 3


def test_launcher_shutdown_terminates_managed_process(tmp_path: Path):
    runtime = _Runtime(tmp_path)
    launcher = PinchTabLauncher(runtime=runtime)
    proc = _Proc()
    launcher._proc = proc
    runtime.logs_dir().mkdir(parents=True, exist_ok=True)
    launcher._log_handle = runtime.log_path().open("ab")
    launcher._write_managed_pid(proc.pid)

    result = launcher.shutdown()

    assert result["ok"] is True
    assert result["stopped"] is True
    assert proc.terminated is True
    assert launcher._proc is None
    assert launcher._log_handle is None
    assert runtime.pid_path().exists() is False


def test_launcher_accepts_status_ok_health_payload(tmp_path: Path, monkeypatch):
    runtime = _Runtime(tmp_path)
    launcher = PinchTabLauncher(runtime=runtime)

    class _Client:
        def runtime_status(self):
            return {"base_url": "http://127.0.0.1:9867"}

        def health(self):
            return {"status": "ok", "mode": "dashboard"}

    monkeypatch.setattr(launcher, "_client", _Client())

    assert launcher._is_healthy() is True
