from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.pinchtab_client import get_pinchtab_client
from app.services.pinchtab_runtime import PinchTabRuntime, get_pinchtab_runtime
from app.settings import settings

_log = logging.getLogger(__name__)
_CREATE_NO_WINDOW = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _tail_text(path: Path, max_chars: int = 4000) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    if len(data) <= max_chars:
        return data
    return data[-max_chars:]


class PinchTabLauncher:
    def __init__(self, runtime: PinchTabRuntime | None = None) -> None:
        self._runtime = runtime or get_pinchtab_runtime()
        self._client = get_pinchtab_client()
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_handle: Any | None = None

    def _base_server_config(self) -> tuple[str, str]:
        parsed = urlparse(self._client.runtime_status().get("base_url") or settings.pinchtab_base_url)
        host = str(parsed.hostname or "127.0.0.1")
        port = str(parsed.port or 9867)
        bind = "127.0.0.1" if host in {"localhost", "127.0.0.1"} else host
        return bind, port

    def _managed_pid_path(self) -> Path:
        return self._runtime.pid_path()

    def _read_managed_pid(self) -> int:
        path = self._managed_pid_path()
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore").strip()
            return max(0, int(raw))
        except Exception:
            return 0

    def _write_managed_pid(self, pid: int) -> None:
        path = self._managed_pid_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{max(0, int(pid))}\n", encoding="utf-8")

    def _clear_managed_pid(self) -> None:
        try:
            self._managed_pid_path().unlink(missing_ok=True)
        except Exception:
            pass

    def _pid_is_running(self, pid: int) -> bool:
        safe_pid = max(0, int(pid or 0))
        if safe_pid <= 0:
            return False
        if os.name == "nt":
            try:
                completed = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {safe_pid}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=5,
                    creationflags=_CREATE_NO_WINDOW,
                )
            except Exception:
                return False
            if completed.returncode != 0:
                return False
            text = " ".join((completed.stdout or "").split()).strip()
            if not text:
                return False
            if "No tasks are running" in text:
                return False
            return str(safe_pid) in text
        try:
            os.kill(safe_pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return False
        return True

    def _terminate_pid_tree(self, pid: int) -> bool:
        safe_pid = max(0, int(pid or 0))
        if safe_pid <= 0:
            return False
        if os.name == "nt":
            try:
                completed = subprocess.run(
                    ["taskkill", "/pid", str(safe_pid), "/t", "/f"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=max(2.0, float(settings.pinchtab_shutdown_timeout_seconds) + 2.0),
                    creationflags=_CREATE_NO_WINDOW,
                )
                return completed.returncode == 0 or (not self._pid_is_running(safe_pid))
            except Exception:
                return False
        try:
            os.kill(safe_pid, signal.SIGTERM)
        except Exception:
            return False
        deadline = time.monotonic() + max(1.0, float(settings.pinchtab_shutdown_timeout_seconds))
        while time.monotonic() < deadline:
            if not self._pid_is_running(safe_pid):
                return True
            time.sleep(0.1)
        try:
            os.kill(safe_pid, signal.SIGKILL)
        except Exception:
            pass
        return not self._pid_is_running(safe_pid)

    def _runtime_status(self) -> dict[str, Any]:
        base = self._runtime.status()
        proc = self._proc
        stored_pid = self._read_managed_pid()
        return {
            **base,
            "managed_pid": int(proc.pid) if proc and proc.poll() is None else stored_pid,
            "managed_process_running": bool(proc and proc.poll() is None) or self._pid_is_running(stored_pid),
        }

    def _health_payload(self) -> dict[str, Any]:
        out = self._client.health()
        if not isinstance(out, dict):
            return {"ok": False, "error": "pinchtab_health_invalid_payload"}
        return out

    def _is_healthy(self) -> bool:
        payload = self._health_payload()
        if bool(payload.get("ok")):
            return True
        return str(payload.get("status") or "").strip().lower() == "ok"

    def _ensure_dirs(self) -> None:
        for path in [
            self._runtime.data_dir(),
            self._runtime.browser_data_dir(),
            self._runtime.profiles_dir(),
            self._runtime.logs_dir(),
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def _config_payload(self) -> dict[str, Any]:
        bind, port = self._base_server_config()
        return {
            "server": {
                "bind": bind,
                "port": port,
                "stateDir": str(self._runtime.data_dir()),
            },
            "profiles": {
                "baseDir": str(self._runtime.profiles_dir()),
                "defaultProfile": "default",
            },
            "instanceDefaults": {
                "mode": "headless",
            },
        }

    def _write_config(self) -> Path:
        config_path = self._runtime.config_path()
        payload = self._config_payload()
        config_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return config_path

    def _close_log_handle(self) -> None:
        if self._log_handle is None:
            return
        try:
            self._log_handle.close()
        except Exception:
            pass
        self._log_handle = None

    def _clear_exited_process_locked(self) -> None:
        proc = self._proc
        if proc is None:
            self._close_log_handle()
            return
        if proc.poll() is None:
            return
        self._proc = None
        self._close_log_handle()
        self._clear_managed_pid()

    def _spawn_locked(self) -> tuple[subprocess.Popen[bytes] | None, str]:
        executable = self._runtime.resolved_executable_path()
        if executable is None:
            return None, "pinchtab_runtime_missing"
        self._ensure_dirs()
        config_path = self._write_config()
        log_path = self._runtime.log_path()
        log_handle = open(log_path, "ab")
        env = {
            **dict(os.environ),
            "PINCHTAB_CONFIG": str(config_path),
            "PINCHTAB_AUTO_LAUNCH": "0",
        }
        bind, port = self._base_server_config()
        env["PINCHTAB_BIND"] = bind
        env["PINCHTAB_PORT"] = port
        try:
            proc = subprocess.Popen(
                [str(executable)],
                cwd=str(executable.parent),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=_CREATE_NO_WINDOW,
                env=env,
            )
        except Exception:
            log_handle.close()
            raise
        self._log_handle = log_handle
        self._proc = proc
        self._write_managed_pid(proc.pid)
        return proc, ""

    def _wait_until_healthy(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                return False
            if self._is_healthy():
                return True
            time.sleep(0.25)
        return False

    def ensure_started(self) -> dict[str, Any]:
        with self._lock:
            self._clear_exited_process_locked()

            if self._is_healthy():
                return {
                    "ok": True,
                    "status": "already_running",
                    **self._runtime_status(),
                }

            stored_pid = self._read_managed_pid()
            if stored_pid > 0 and self._pid_is_running(stored_pid):
                self._terminate_pid_tree(stored_pid)
                self._clear_managed_pid()

            try:
                proc, error = self._spawn_locked()
            except Exception as exc:
                return {
                    "ok": False,
                    "error": f"pinchtab_launch_failed:{exc}",
                    **self._runtime_status(),
                }

            if proc is None:
                return {
                    "ok": False,
                    "error": error or "pinchtab_runtime_missing",
                    **self._runtime_status(),
                }

        if self._wait_until_healthy(settings.pinchtab_startup_timeout_seconds):
            return {
                "ok": True,
                "status": "started",
                **self._runtime_status(),
            }

        log_excerpt = _tail_text(self._runtime.log_path())
        self.shutdown()
        return {
            "ok": False,
            "error": "pinchtab_start_timeout",
            "log_excerpt": log_excerpt,
            **self._runtime_status(),
        }

    def shutdown(self) -> dict[str, Any]:
        with self._lock:
            proc = self._proc
            stored_pid = self._read_managed_pid()
            stopped = False

            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=max(1.0, float(settings.pinchtab_shutdown_timeout_seconds)))
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                stopped = True

            if stored_pid > 0 and self._pid_is_running(stored_pid):
                stopped = self._terminate_pid_tree(stored_pid) or stopped

            self._proc = None
            self._close_log_handle()
            self._clear_managed_pid()
            return {"ok": True, "stopped": stopped, **self._runtime_status()}


_pinchtab_launcher: PinchTabLauncher | None = None


def get_pinchtab_launcher() -> PinchTabLauncher:
    global _pinchtab_launcher
    if _pinchtab_launcher is None:
        _pinchtab_launcher = PinchTabLauncher()
    return _pinchtab_launcher


def ensure_pinchtab_started() -> dict[str, Any]:
    return get_pinchtab_launcher().ensure_started()


def shutdown_pinchtab_launcher() -> dict[str, Any]:
    return get_pinchtab_launcher().shutdown()
