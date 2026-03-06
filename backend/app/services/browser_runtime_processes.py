from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None

if TYPE_CHECKING:
    from app.services.browser_automation import BrowserSession

_BROWSER_FAMILY_NAMES = {
    "chrome",
    "chrome.exe",
    "msedge",
    "msedge.exe",
    "firefox",
    "firefox.exe",
    "chromium",
    "chromium.exe",
    "opera",
    "opera.exe",
    "brave",
    "brave.exe",
}
_CHROMIUM_FAMILIES = {"chrome", "chromium", "edge", "brave", "opera"}
_BROWSER_NAME_TOKENS = ("chrome", "edge", "firefox", "opera", "brave", "chromium")


def _normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


class BrowserProcessRuntimeMixin:
    @staticmethod
    def _guess_browser_family(name: str, exe: str, cmdline: str) -> str:
        blob = " ".join([str(name or "").lower(), str(exe or "").lower(), str(cmdline or "").lower()])
        if "msedge" in blob or "edge" in blob:
            return "edge"
        if "firefox" in blob:
            return "firefox"
        if "brave" in blob:
            return "brave"
        if "opera" in blob:
            return "opera"
        if "chromium" in blob:
            return "chromium"
        if "chrome" in blob:
            return "chrome"
        return "unknown"

    @staticmethod
    def _is_browser_name(name: str) -> bool:
        low_name = str(name or "").strip().lower()
        if not low_name:
            return False
        if low_name in _BROWSER_FAMILY_NAMES:
            return True
        return any(token in low_name for token in _BROWSER_NAME_TOKENS)

    @staticmethod
    def _is_chromium_name(name: str) -> bool:
        low_name = str(name or "").strip().lower()
        if not low_name:
            return False
        if "msedge" in low_name or "edge" in low_name:
            return True
        return any(token in low_name for token in ("chrome", "chromium", "brave", "opera"))

    def _collect_browser_pids(self, *, pid: int = 0) -> list[dict[str, Any]]:
        if psutil is None:
            return []
        out: list[dict[str, Any]] = []
        for proc in psutil.process_iter(attrs=["pid", "name"]):
            try:
                info = proc.info if isinstance(getattr(proc, "info", None), dict) else {}
                proc_pid = int(info.get("pid") or 0)
                if proc_pid <= 0:
                    continue
                if pid > 0 and proc_pid != int(pid):
                    continue
                name = str(info.get("name") or "").strip()
                if not self._is_browser_name(name):
                    continue
                out.append(
                    {
                        "pid": proc_pid,
                        "name": name[:80],
                        "browser_family": self._guess_browser_family(name, "", ""),
                        "status": "",
                        "started_at": 0.0,
                        "memory_mb": 0.0,
                        "exe": "",
                        "cmdline": "",
                    }
                )
            except Exception:
                continue
        return out

    def _fill_process_details(self, rows: list[dict[str, Any]], *, max_probe: int) -> None:
        if psutil is None or not rows:
            return
        probe_limit = max(0, int(max_probe or 0))
        if probe_limit <= 0:
            return
        for row in rows[:probe_limit]:
            try:
                proc = psutil.Process(int(row.get("pid") or 0))
            except Exception:
                continue
            try:
                exe = str(proc.exe() or "").strip()
            except Exception:
                exe = ""
            try:
                cmdline = " ".join([str(part) for part in (proc.cmdline() or []) if str(part or "").strip()]).strip()
            except Exception:
                cmdline = ""
            try:
                rss = int(getattr(proc.memory_info(), "rss", 0) or 0)
            except Exception:
                rss = 0
            if exe:
                row["exe"] = exe[:260]
            if cmdline:
                row["cmdline"] = cmdline[:600]
            row["memory_mb"] = round(rss / (1024 * 1024), 2) if rss > 0 else 0.0
            if str(row.get("browser_family") or "") in {"", "unknown"}:
                row["browser_family"] = self._guess_browser_family(str(row.get("name") or ""), exe, cmdline)

    def _list_system_browser_processes(
        self,
        *,
        max_items: int,
        pid: int = 0,
        include_details: bool = False,
    ) -> list[dict[str, Any]]:
        if psutil is None:
            return []
        raw_limit = 20 if max_items is None else int(max_items)
        limit = max(0, min(200, raw_limit))
        if limit <= 0:
            return []
        cache_key = (int(pid or 0), bool(include_details))
        now = time.time()
        with self._system_process_cache_lock:
            cached = self._system_process_cache.get(cache_key)
        if cached:
            ts, payload = cached
            if (now - float(ts)) <= max(0.2, float(self._system_process_cache_ttl_seconds)):
                return list(payload)[:limit]

        rows = self._collect_browser_pids(pid=int(pid or 0))
        if include_details:
            self._fill_process_details(rows, max_probe=min(limit, 8))
        rows.sort(key=lambda it: (float(it.get("memory_mb") or 0.0), int(it.get("pid") or 0)), reverse=True)
        trimmed = rows[:limit]
        with self._system_process_cache_lock:
            self._system_process_cache[cache_key] = (now, list(trimmed))
        return trimmed

    def _has_system_browser_process(self, *, pid: int = 0) -> bool:
        if psutil is None:
            return False
        target_pid = int(pid or 0)
        for proc in psutil.process_iter(attrs=["pid", "name"]):
            try:
                info = proc.info if isinstance(getattr(proc, "info", None), dict) else {}
                proc_pid = int(info.get("pid") or 0)
                if proc_pid <= 0:
                    continue
                if target_pid > 0 and proc_pid != target_pid:
                    continue
                if self._is_browser_name(str(info.get("name") or "")):
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _is_cdp_conflict_row(row: dict[str, Any]) -> bool:
        family = str(row.get("browser_family") or "").strip().lower()
        if family in _CHROMIUM_FAMILIES:
            return True
        blob = " ".join(
            [
                str(row.get("name") or "").lower(),
                str(row.get("exe") or "").lower(),
                str(row.get("cmdline") or "").lower(),
            ]
        )
        return any(token in blob for token in ("chrome", "chromium", "msedge", "edge", "brave", "opera"))

    @staticmethod
    def _extract_connection_port(laddr: Any) -> int:
        if laddr is None:
            return 0
        try:
            if hasattr(laddr, "port"):
                return int(getattr(laddr, "port") or 0)
        except Exception:
            pass
        try:
            if isinstance(laddr, (tuple, list)) and len(laddr) >= 2:
                return int(laddr[1] or 0)
        except Exception:
            pass
        return 0

    def _has_cdp_conflict_process(self) -> bool:
        return bool(self._list_cdp_conflict_processes(max_items=1))

    def _collect_sessions_by_mode(
        self,
        mode: str,
        *,
        user_id: int | None = None,
        workspace: str = "",
        profile_id: str = "",
    ) -> list[BrowserSession]:
        target = str(mode or "").strip().lower()
        target_workspace = _normalize_workspace(workspace) if str(workspace or "").strip() else ""
        target_profile_id = (
            self._resolved_profile_id(workspace=target_workspace or "default", profile_id=profile_id)
            if str(profile_id or "").strip()
            else ""
        )
        out: list[BrowserSession] = []
        with self._lock:
            remove_keys: list[str] = []
            for key, session in self._sessions.items():
                if str(getattr(session, "mode", "") or "").strip().lower() != target:
                    continue
                if user_id is not None and int(getattr(session, "user_id", 0) or 0) != int(user_id):
                    continue
                if target_workspace and _normalize_workspace(str(getattr(session, "workspace", "") or "")) != target_workspace:
                    continue
                if target_profile_id and str(getattr(session, "profile_id", "") or "").strip() != target_profile_id:
                    continue
                remove_keys.append(key)
            for key in remove_keys:
                session = self._sessions.pop(key, None)
                if session is not None:
                    out.append(session)
        return out

    def _close_sessions_by_mode(
        self,
        mode: str,
        *,
        user_id: int | None = None,
        workspace: str = "",
        profile_id: str = "",
    ) -> None:
        sessions = self._collect_sessions_by_mode(
            mode,
            user_id=user_id,
            workspace=workspace,
            profile_id=profile_id,
        )
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass

    def _terminate_processes(self, pids: list[int], *, wait_timeout_seconds: float = 4.0) -> dict[str, Any]:
        safe_pids = sorted({int(pid) for pid in pids if int(pid) > 0 and int(pid) != os.getpid()})
        if not safe_pids:
            return {"terminated_pids": [], "killed_pids": [], "failed_pids": []}
        if psutil is None:
            return {"terminated_pids": [], "killed_pids": [], "failed_pids": safe_pids}

        terminated: list[int] = []
        killed: list[int] = []
        failed: list[int] = []
        processes: list[Any] = []

        for pid in safe_pids:
            try:
                proc = psutil.Process(pid)
            except Exception:
                continue
            try:
                proc.terminate()
                processes.append(proc)
                terminated.append(pid)
            except Exception:
                failed.append(pid)

        if processes:
            try:
                _, alive = psutil.wait_procs(processes, timeout=max(0.5, float(wait_timeout_seconds)))
            except Exception:
                alive = processes
            for proc in alive:
                try:
                    proc.kill()
                    killed.append(int(getattr(proc, "pid", 0) or 0))
                except Exception:
                    failed.append(int(getattr(proc, "pid", 0) or 0))

        return {
            "terminated_pids": sorted({pid for pid in terminated if pid > 0}),
            "killed_pids": sorted({pid for pid in killed if pid > 0}),
            "failed_pids": sorted({pid for pid in failed if pid > 0}),
        }
