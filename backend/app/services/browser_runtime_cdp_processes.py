from __future__ import annotations

import os
from typing import Any

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None


class BrowserCdpProcessRuntimeMixin:
    def _list_chromium_family_pids(self, *, max_items: int = 200) -> list[int]:
        if psutil is None:
            return []
        raw_limit = 20 if max_items is None else int(max_items)
        limit = max(0, min(400, raw_limit))
        if limit <= 0:
            return []
        out: list[int] = []
        for proc in psutil.process_iter(attrs=["pid", "name"]):
            try:
                info = proc.info if isinstance(getattr(proc, "info", None), dict) else {}
                pid = int(info.get("pid") or 0)
                if pid <= 0:
                    continue
                if self._is_chromium_name(str(info.get("name") or "")):
                    out.append(pid)
            except Exception:
                continue
        deduped = sorted({int(pid) for pid in out if int(pid) > 0 and int(pid) != os.getpid()})
        return deduped[:limit]

    def _list_port_listener_pids(self, *, port: int) -> list[int]:
        if psutil is None:
            return []
        target = int(port or 0)
        if target <= 0:
            return []
        out: set[int] = set()
        try:
            conns = psutil.net_connections(kind="inet")
        except Exception:
            return []
        for conn in conns:
            try:
                local_port = self._extract_connection_port(getattr(conn, "laddr", None))
            except Exception:
                local_port = 0
            if int(local_port or 0) != target:
                continue
            status = str(getattr(conn, "status", "") or "").strip().upper()
            if status and status not in {"LISTEN", "NONE"}:
                continue
            pid = int(getattr(conn, "pid", 0) or 0)
            if pid > 0:
                out.add(pid)
        return sorted(out)

    def _list_cdp_conflict_processes(self, *, max_items: int = 200, endpoint: str = "") -> list[dict[str, Any]]:
        if psutil is None:
            return []
        raw_limit = 20 if max_items is None else int(max_items)
        limit = max(0, min(200, raw_limit))
        if limit <= 0:
            return []
        endpoint_text = str(endpoint or self._cdp_endpoint or "").strip()
        port = self._parse_cdp_port(endpoint_text)
        if port <= 0:
            return []
        pids = self._list_port_listener_pids(port=port)
        if not pids:
            return []

        rows: list[dict[str, Any]] = []
        for pid in pids[:limit]:
            try:
                proc = psutil.Process(int(pid))
            except Exception:
                continue
            try:
                name = str(proc.name() or "").strip()
            except Exception:
                name = ""
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
            rows.append(
                {
                    "pid": int(pid),
                    "name": name[:80],
                    "browser_family": self._guess_browser_family(name, exe, cmdline),
                    "status": "port_conflict",
                    "started_at": 0.0,
                    "memory_mb": round(rss / (1024 * 1024), 2) if rss > 0 else 0.0,
                    "exe": exe[:260],
                    "cmdline": cmdline[:600],
                    "port": int(port),
                }
            )
        rows.sort(key=lambda it: (float(it.get("memory_mb") or 0.0), int(it.get("pid") or 0)), reverse=True)
        return rows[:limit]
