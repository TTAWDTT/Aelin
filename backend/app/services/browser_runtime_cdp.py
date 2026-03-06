from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None

def _normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


class BrowserCdpRuntimeMixin:
    @staticmethod
    def _parse_cdp_port(endpoint: str) -> int:
        matched = re.match(r"^https?://(?:127\.0\.0\.1|localhost):(\d{2,5})/?$", str(endpoint or "").strip(), flags=re.I)
        if not matched:
            return 0
        try:
            port = int(matched.group(1))
        except Exception:
            return 0
        if port < 1 or port > 65535:
            return 0
        return port

    def _probe_cdp_endpoint(self, endpoint: str, *, timeout_seconds: float = 0.35) -> bool:
        ok, _reason = self._probe_cdp_endpoint_with_reason(endpoint, timeout_seconds=timeout_seconds)
        return bool(ok)

    def _probe_cdp_endpoint_with_reason(
        self, endpoint: str, *, timeout_seconds: float = 0.35
    ) -> tuple[bool, str]:
        target = str(endpoint or "").strip().rstrip("/")
        if not target:
            return False, "endpoint_empty"
        url = f"{target}/json/version"
        try:
            with urllib.request.urlopen(url, timeout=max(0.2, float(timeout_seconds))) as resp:
                status_code = int(getattr(resp, "status", 200) or 200)
                if status_code >= 400:
                    return False, f"http_status_{status_code}"
                payload = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
            if not isinstance(payload, dict):
                return False, "invalid_json_payload"
            websocket_url = str(payload.get("webSocketDebuggerUrl") or "").strip()
            if not websocket_url:
                return False, "missing_websocket_debugger_url"
            return True, "ok"
        except urllib.error.HTTPError as exc:
            return False, f"http_error_{int(getattr(exc, 'code', 0) or 0)}"
        except urllib.error.URLError as exc:
            reason = str(getattr(exc, "reason", "") or "").strip()
            if reason:
                return False, f"url_error:{reason[:80]}"
            return False, "url_error"
        except TimeoutError:
            return False, "timeout"
        except ValueError:
            return False, "invalid_json"
        except Exception:
            return False, "unexpected_exception"

    def _collect_cdp_probe_snapshot(self, endpoint: str, *, timeout_seconds: float = 0.4) -> dict[str, Any]:
        ok, reason = self._probe_cdp_endpoint_with_reason(endpoint, timeout_seconds=timeout_seconds)
        port = self._parse_cdp_port(endpoint)
        listeners = self._list_port_listener_pids(port=port) if port > 0 else []
        return {
            "ok": bool(ok),
            "reason": str(reason or "unknown"),
            "endpoint": str(endpoint or "")[:160],
            "port": int(port),
            "listener_count": len(listeners),
            "listener_pids": [int(pid) for pid in listeners[:8]],
        }

    @staticmethod
    def _select_first_existing_path(candidates: list[str]) -> str:
        seen: set[str] = set()
        for item in candidates:
            norm = str(item or "").strip()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            if Path(norm).exists():
                return norm
        return ""

    def _list_cft_browser_candidates(self) -> list[str]:
        candidates: list[str] = []
        if os.name != "nt":
            return candidates
        local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
        program_files = str(os.environ.get("ProgramFiles") or "").strip()
        program_files_x86 = str(os.environ.get("ProgramFiles(x86)") or "").strip()
        windows_paths = [
            (local_app_data, "Google/Chrome for Testing/Application/chrome.exe"),
            (program_files, "Google/Chrome for Testing/Application/chrome.exe"),
            (program_files_x86, "Google/Chrome for Testing/Application/chrome.exe"),
            (local_app_data, "GoogleChromeLabs/chrome-for-testing/chrome.exe"),
            (program_files, "GoogleChromeLabs/chrome-for-testing/chrome.exe"),
            (program_files_x86, "GoogleChromeLabs/chrome-for-testing/chrome.exe"),
        ]
        for base, suffix in windows_paths:
            if not base:
                continue
            candidates.append(str(Path(base) / suffix))
        return candidates

    def _list_system_browser_candidates(self) -> list[str]:
        candidates: list[str] = []
        for name in ("chrome", "msedge", "chromium", "brave", "brave-browser"):
            resolved = shutil.which(name)
            if resolved:
                candidates.append(str(resolved))

        if os.name == "nt":
            local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
            program_files = str(os.environ.get("ProgramFiles") or "").strip()
            program_files_x86 = str(os.environ.get("ProgramFiles(x86)") or "").strip()
            windows_paths = [
                (local_app_data, "Google/Chrome/Application/chrome.exe"),
                (program_files, "Google/Chrome/Application/chrome.exe"),
                (program_files_x86, "Google/Chrome/Application/chrome.exe"),
                (local_app_data, "Microsoft/Edge/Application/msedge.exe"),
                (program_files, "Microsoft/Edge/Application/msedge.exe"),
                (program_files_x86, "Microsoft/Edge/Application/msedge.exe"),
            ]
            for base, suffix in windows_paths:
                if not base:
                    continue
                candidates.append(str(Path(base) / suffix))
        return candidates

    def _resolve_cdp_browser_executable(self) -> str:
        configured = str(self._cdp_browser_path or "").strip()
        if configured:
            candidate = Path(configured).expanduser()
            if candidate.exists():
                return str(candidate)
        cft = self._select_first_existing_path(self._list_cft_browser_candidates())
        if cft:
            return cft
        return self._select_first_existing_path(self._list_system_browser_candidates())

    def _resolve_cdp_profile_dir(self, *, user_id: int, workspace: str, profile_id: str = "") -> Path:
        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        normalized_workspace = _normalize_workspace(workspace)
        user_segment = f"user_{int(user_id)}"
        workspace_segment = self._sanitize_profile_segment(normalized_workspace, default="default")
        profile_segment = self._sanitize_profile_segment(resolved_profile_id, default="default")
        target = self._cdp_profile_dir / user_segment / workspace_segment / profile_segment
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _normalize_path_value(path: str | Path | None) -> str:
        raw = str(path or "").strip()
        if not raw:
            return ""
        try:
            return str(Path(raw).resolve())
        except Exception:
            return str(Path(raw))

    @staticmethod
    def _extract_user_data_dir_from_cmdline(cmdline: str) -> str:
        text = str(cmdline or "").strip()
        if not text:
            return ""
        patterns = (
            r'--user-data-dir="([^"]+)"',
            r"--user-data-dir=([^\s]+)",
            r'--user-data-dir\s+"([^"]+)"',
            r"--user-data-dir\s+([^\s]+)",
        )
        for pattern in patterns:
            matched = re.search(pattern, text, flags=re.I)
            if matched:
                return str(matched.group(1) or "").strip().strip('"')
        return ""

    def _get_cdp_listener_user_data_dir(self, *, endpoint: str) -> str:
        conflicts = self._list_cdp_conflict_processes(max_items=8, endpoint=endpoint)
        for row in conflicts:
            cmdline = str(row.get("cmdline") or "")
            user_data_dir = self._extract_user_data_dir_from_cmdline(cmdline)
            normalized = self._normalize_path_value(user_data_dir)
            if normalized:
                return normalized
        return ""

    def _remember_active_cdp_profile(
        self,
        *,
        user_id: int,
        workspace: str,
        profile_id: str = "",
        user_data_dir: str = "",
    ) -> None:
        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        profile_key = self._profile_key(user_id=user_id, workspace=workspace, profile_id=resolved_profile_id)
        with self._lock:
            self._active_cdp_profile_key = profile_key
            self._active_cdp_user_data_dir = self._normalize_path_value(user_data_dir)

    def _clear_active_cdp_profile(self) -> None:
        with self._lock:
            self._active_cdp_profile_key = ""
            self._active_cdp_user_data_dir = ""

    def _is_target_cdp_profile_active(self, *, user_id: int, workspace: str, profile_id: str = "") -> bool:
        target_dir = self._normalize_path_value(
            self._resolve_cdp_profile_dir(user_id=user_id, workspace=workspace, profile_id=profile_id)
        )
        if not target_dir:
            return False
        active_dir = self._get_cdp_listener_user_data_dir(endpoint=self._cdp_endpoint)
        if active_dir:
            return active_dir == target_dir
        target_profile_key = self._profile_key(
            user_id=user_id,
            workspace=workspace,
            profile_id=self._resolved_profile_id(workspace=workspace, profile_id=profile_id),
        )
        with self._lock:
            remembered_key = str(self._active_cdp_profile_key or "")
            remembered_dir = str(self._active_cdp_user_data_dir or "")
        if remembered_dir:
            return self._normalize_path_value(remembered_dir) == target_dir
        return bool(remembered_key) and remembered_key == target_profile_key

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

