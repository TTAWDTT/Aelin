from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

_LOG = logging.getLogger(__name__)


class BrowserCdpLifecycleRuntimeMixin:
    def _build_cdp_launch_command(
        self,
        endpoint: str,
        *,
        user_id: int,
        workspace: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        exe = self._resolve_cdp_browser_executable()
        if not exe:
            raise RuntimeError("cdp_browser_not_found")
        port = self._parse_cdp_port(endpoint)
        if port <= 0:
            raise RuntimeError("cdp_endpoint_invalid")
        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        user_data_dir = self._resolve_cdp_profile_dir(
            user_id=user_id,
            workspace=workspace,
            profile_id=resolved_profile_id,
        )
        cmd = [
            exe,
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            "about:blank",
        ]
        return {
            "cmd": cmd,
            "exe": exe,
            "port": int(port),
            "user_data_dir": str(user_data_dir),
            "profile_id": resolved_profile_id,
        }

    def _launch_cdp_browser(
        self,
        endpoint: str,
        *,
        user_id: int,
        workspace: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        launch = self._build_cdp_launch_command(
            endpoint,
            user_id=user_id,
            workspace=workspace,
            profile_id=profile_id,
        )
        _LOG.info(
            "cdp_launch command exe=%s port=%s user_data_dir=%s profile_id=%s",
            str(launch.get("exe") or "")[:180],
            int(launch.get("port") or 0),
            str(launch.get("user_data_dir") or "-")[:220],
            str(launch.get("profile_id") or "")[:120],
        )
        try:
            child = subprocess.Popen(
                list(launch.get("cmd") or []),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.35)
            exit_code = child.poll()
            launch_meta = {
                "pid": int(getattr(child, "pid", 0) or 0),
                "endpoint": str(endpoint)[:160],
                "alive": exit_code is None,
                "exit_code": None if exit_code is None else int(exit_code),
                "user_data_dir": str(launch.get("user_data_dir") or "")[:220],
                "profile_id": str(launch.get("profile_id") or "")[:120],
            }
            _LOG.info(
                "cdp_launch spawned pid=%s endpoint=%s alive=%s exit_code=%s profile_id=%s",
                int(launch_meta.get("pid") or 0),
                str(launch_meta.get("endpoint") or "")[:160],
                "1" if bool(launch_meta.get("alive")) else "0",
                "" if launch_meta.get("exit_code") is None else str(launch_meta.get("exit_code")),
                str(launch_meta.get("profile_id") or "")[:120],
            )
            return launch_meta
        except Exception as exc:
            raise RuntimeError(f"cdp_launch_failed:{str(exc)[:120]}") from exc

    def _wait_for_cdp_endpoint(
        self,
        endpoint: str,
        *,
        deadline: float,
        probe_timeout_seconds: float = 0.35,
        sleep_seconds: float = 0.2,
    ) -> tuple[bool, int]:
        attempts = 0
        while time.time() < deadline:
            attempts += 1
            if self._probe_cdp_endpoint(endpoint, timeout_seconds=probe_timeout_seconds):
                return True, attempts
            time.sleep(sleep_seconds)
        return False, attempts

    def _recommended_restart_timeout_seconds(self) -> float:
        launch_budget = max(8.0, float(self._cdp_launch_timeout_seconds or 10.0))
        return max(18.0, launch_budget + 10.0)

    def _ensure_cdp_endpoint_ready(self, *, user_id: int, workspace: str, profile_id: str = "") -> None:
        endpoint = str(self._cdp_endpoint or "").strip()
        probe_attempts = 0
        launch_meta: dict[str, Any] | None = None
        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        if not endpoint:
            raise RuntimeError("cdp_endpoint_unconfigured")
        if self._probe_cdp_endpoint(endpoint, timeout_seconds=0.25):
            if self._is_target_cdp_profile_active(
                user_id=user_id,
                workspace=workspace,
                profile_id=resolved_profile_id,
            ):
                self._remember_active_cdp_profile(
                    user_id=user_id,
                    workspace=workspace,
                    profile_id=resolved_profile_id,
                    user_data_dir=self._get_cdp_listener_user_data_dir(endpoint=endpoint),
                )
                return
            raise RuntimeError("cdp_requires_browser_restart")
        if not self._cdp_auto_launch:
            raise RuntimeError("cdp_endpoint_unavailable")

        with self._cdp_bootstrap_lock:
            if self._probe_cdp_endpoint(endpoint, timeout_seconds=0.25):
                if self._is_target_cdp_profile_active(
                    user_id=user_id,
                    workspace=workspace,
                    profile_id=resolved_profile_id,
                ):
                    self._remember_active_cdp_profile(
                        user_id=user_id,
                        workspace=workspace,
                        profile_id=resolved_profile_id,
                        user_data_dir=self._get_cdp_listener_user_data_dir(endpoint=endpoint),
                    )
                    return
                raise RuntimeError("cdp_requires_browser_restart")
            launch_meta = self._launch_cdp_browser(
                endpoint,
                user_id=user_id,
                workspace=workspace,
                profile_id=resolved_profile_id,
            )
            deadline = time.time() + max(2.0, float(self._cdp_launch_timeout_seconds or 10.0))
            ready, probe_attempts = self._wait_for_cdp_endpoint(
                endpoint,
                deadline=deadline,
                probe_timeout_seconds=0.35,
                sleep_seconds=0.2,
            )
            if ready:
                self._remember_active_cdp_profile(
                    user_id=user_id,
                    workspace=workspace,
                    profile_id=resolved_profile_id,
                    user_data_dir=str(launch_meta.get("user_data_dir") or ""),
                )
                return
            conflicts = self._list_cdp_conflict_processes(max_items=8, endpoint=endpoint)
            if conflicts:
                diag = self._collect_cdp_probe_snapshot(endpoint, timeout_seconds=0.5)
                _LOG.warning(
                    "ensure_cdp_endpoint_ready requires_restart endpoint=%s attempts=%s reason=%s listeners=%s launch_pid=%s launch_alive=%s launch_exit_code=%s profile_id=%s",
                    str(endpoint)[:160],
                    int(probe_attempts),
                    str(diag.get("reason") or "unknown")[:120],
                    int(diag.get("listener_count") or 0),
                    int((launch_meta or {}).get("pid") or 0),
                    "1" if bool((launch_meta or {}).get("alive")) else "0",
                    "" if (launch_meta or {}).get("exit_code") is None else str((launch_meta or {}).get("exit_code")),
                    resolved_profile_id[:120],
                )
                raise RuntimeError("cdp_requires_browser_restart")
        diag = self._collect_cdp_probe_snapshot(endpoint, timeout_seconds=0.5)
        _LOG.warning(
            "ensure_cdp_endpoint_ready timeout endpoint=%s attempts=%s reason=%s listeners=%s launch_pid=%s launch_alive=%s launch_exit_code=%s profile_id=%s",
            str(endpoint)[:160],
            int(probe_attempts),
            str(diag.get("reason") or "unknown")[:120],
            int(diag.get("listener_count") or 0),
            int((launch_meta or {}).get("pid") or 0),
            "1" if bool((launch_meta or {}).get("alive")) else "0",
            "" if (launch_meta or {}).get("exit_code") is None else str((launch_meta or {}).get("exit_code")),
            resolved_profile_id[:120],
        )
        raise RuntimeError("cdp_launch_timeout")

    def force_restart_to_cdp(
        self,
        *,
        timeout_seconds: float = 12.0,
        user_id: int = 0,
        workspace: str = "default",
        profile_id: str = "",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        endpoint = str(self._cdp_endpoint or "").strip()
        last_launch_meta: dict[str, Any] | None = None
        resolved_profile_id = self._resolved_profile_id(workspace=workspace, profile_id=profile_id)
        if not endpoint:
            _LOG.warning("force_restart_to_cdp failed: endpoint_unconfigured")
            return {"ok": False, "error": "cdp_endpoint_unconfigured"}
        if self._probe_cdp_endpoint(endpoint, timeout_seconds=0.4) and self._is_target_cdp_profile_active(
            user_id=user_id,
            workspace=workspace,
            profile_id=resolved_profile_id,
        ):
            self._remember_active_cdp_profile(
                user_id=user_id,
                workspace=workspace,
                profile_id=resolved_profile_id,
                user_data_dir=self._get_cdp_listener_user_data_dir(endpoint=endpoint),
            )
            _LOG.info(
                "force_restart_to_cdp skipped: already_ready endpoint=%s latency_ms=%s profile_id=%s",
                endpoint,
                int((time.perf_counter() - started) * 1000),
                resolved_profile_id[:120],
            )
            return {"ok": True, "endpoint": endpoint, "already_ready": True, "profile_id": resolved_profile_id}

        requested_timeout = max(2.0, float(timeout_seconds or 12.0))
        effective_timeout = max(requested_timeout, self._recommended_restart_timeout_seconds())
        _LOG.info(
            "force_restart_to_cdp start endpoint=%s timeout_s=%.2f effective_timeout_s=%.2f",
            endpoint,
            requested_timeout,
            effective_timeout,
        )
        self._close_sessions_by_mode(
            "cdp",
            user_id=user_id,
            workspace=workspace,
            profile_id=resolved_profile_id,
        )
        conflicts = self._list_cdp_conflict_processes(max_items=200, endpoint=endpoint)
        pids = [int(row.get("pid") or 0) for row in conflicts if int(row.get("pid") or 0) > 0]
        terminate_report = self._terminate_processes(pids, wait_timeout_seconds=4.0)
        _LOG.info(
            "force_restart_to_cdp terminate attempted=%s terminated=%s killed=%s failed=%s",
            len(pids),
            len(list(terminate_report.get("terminated_pids") or [])),
            len(list(terminate_report.get("killed_pids") or [])),
            len(list(terminate_report.get("failed_pids") or [])),
        )

        deadline = time.time() + effective_timeout
        while time.time() < deadline:
            if not self._list_cdp_conflict_processes(max_items=1, endpoint=endpoint):
                break
            time.sleep(0.15)

        remaining = self._list_cdp_conflict_processes(max_items=20, endpoint=endpoint)
        if remaining:
            _LOG.warning(
                "force_restart_to_cdp failed: conflicts_remaining=%s pids=%s latency_ms=%s",
                len(remaining),
                ",".join([str(int(row.get("pid") or 0)) for row in remaining[:8]]),
                int((time.perf_counter() - started) * 1000),
            )
            return {
                "ok": False,
                "error": "cdp_conflict_process_still_running",
                "endpoint": endpoint,
                "remaining_pids": [int(row.get("pid") or 0) for row in remaining if int(row.get("pid") or 0) > 0],
                "remaining_processes": [
                    {
                        "pid": int(row.get("pid") or 0),
                        "name": str(row.get("name") or "")[:80],
                        "cmdline": str(row.get("cmdline") or "")[:240],
                        "port": int(row.get("port") or 0),
                    }
                    for row in remaining[:8]
                ],
                **terminate_report,
            }

        with self._cdp_bootstrap_lock:
            if self._probe_cdp_endpoint(endpoint, timeout_seconds=0.35):
                _LOG.info(
                    "force_restart_to_cdp ready_after_cleanup endpoint=%s latency_ms=%s",
                    endpoint,
                    int((time.perf_counter() - started) * 1000),
                )
                return {"ok": True, "endpoint": endpoint, "already_ready": True, **terminate_report}
            try:
                last_launch_meta = self._launch_cdp_browser(
                    endpoint,
                    user_id=user_id,
                    workspace=workspace,
                    profile_id=resolved_profile_id,
                )
            except Exception as exc:
                _LOG.warning(
                    "force_restart_to_cdp launch_failed endpoint=%s error=%s latency_ms=%s",
                    endpoint,
                    str(exc)[:180],
                    int((time.perf_counter() - started) * 1000),
                )
                return {
                    "ok": False,
                    "error": str(exc)[:180] or "cdp_launch_failed",
                    "endpoint": endpoint,
                    **terminate_report,
                }
            ready, _attempts = self._wait_for_cdp_endpoint(
                endpoint,
                deadline=deadline,
                probe_timeout_seconds=0.35,
                sleep_seconds=0.2,
            )
            if ready:
                self._remember_active_cdp_profile(
                    user_id=user_id,
                    workspace=workspace,
                    profile_id=resolved_profile_id,
                    user_data_dir=str((last_launch_meta or {}).get("user_data_dir") or ""),
                )
                _LOG.info(
                    "force_restart_to_cdp success endpoint=%s latency_ms=%s profile_id=%s",
                    endpoint,
                    int((time.perf_counter() - started) * 1000),
                    resolved_profile_id[:120],
                )
                return {"ok": True, "endpoint": endpoint, "profile_id": resolved_profile_id, **terminate_report}
        chromium_pids = self._list_chromium_family_pids(max_items=200)
        if chromium_pids:
            _LOG.warning(
                "force_restart_to_cdp fallback_full_restart attempted=%s endpoint=%s",
                len(chromium_pids),
                endpoint,
            )
            fallback_report = self._terminate_processes(chromium_pids, wait_timeout_seconds=5.0)
            merged_terminated = sorted(
                {
                    *list(terminate_report.get("terminated_pids") or []),
                    *list(fallback_report.get("terminated_pids") or []),
                }
            )
            merged_killed = sorted(
                {
                    *list(terminate_report.get("killed_pids") or []),
                    *list(fallback_report.get("killed_pids") or []),
                }
            )
            merged_failed = sorted(
                {
                    *list(terminate_report.get("failed_pids") or []),
                    *list(fallback_report.get("failed_pids") or []),
                }
            )
            terminate_report = {
                "terminated_pids": merged_terminated,
                "killed_pids": merged_killed,
                "failed_pids": merged_failed,
            }
            try:
                last_launch_meta = self._launch_cdp_browser(
                    endpoint,
                    user_id=user_id,
                    workspace=workspace,
                    profile_id=resolved_profile_id,
                )
            except Exception as exc:
                _LOG.warning(
                    "force_restart_to_cdp fallback_launch_failed endpoint=%s error=%s latency_ms=%s",
                    endpoint,
                    str(exc)[:180],
                    int((time.perf_counter() - started) * 1000),
                )
                return {
                    "ok": False,
                    "error": str(exc)[:180] or "cdp_launch_failed",
                    "endpoint": endpoint,
                    **terminate_report,
                }
            second_deadline = time.time() + max(8.0, min(25.0, effective_timeout))
            ready, _attempts = self._wait_for_cdp_endpoint(
                endpoint,
                deadline=second_deadline,
                probe_timeout_seconds=0.35,
                sleep_seconds=0.2,
            )
            if ready:
                self._remember_active_cdp_profile(
                    user_id=user_id,
                    workspace=workspace,
                    profile_id=resolved_profile_id,
                    user_data_dir=str((last_launch_meta or {}).get("user_data_dir") or ""),
                )
                _LOG.info(
                    "force_restart_to_cdp success_after_fallback endpoint=%s latency_ms=%s profile_id=%s",
                    endpoint,
                    int((time.perf_counter() - started) * 1000),
                    resolved_profile_id[:120],
                )
                return {
                    "ok": True,
                    "endpoint": endpoint,
                    "profile_id": resolved_profile_id,
                    "fallback_full_restart": True,
                    **terminate_report,
                }
        remaining_after_launch = self._list_cdp_conflict_processes(max_items=20, endpoint=endpoint)
        if remaining_after_launch:
            _LOG.warning(
                "force_restart_to_cdp timeout_with_conflicts endpoint=%s conflicts=%s latency_ms=%s",
                endpoint,
                len(remaining_after_launch),
                int((time.perf_counter() - started) * 1000),
            )
            return {
                "ok": False,
                "error": "cdp_conflict_process_still_running",
                "endpoint": endpoint,
                "remaining_pids": [
                    int(row.get("pid") or 0) for row in remaining_after_launch if int(row.get("pid") or 0) > 0
                ],
                "remaining_processes": [
                    {
                        "pid": int(row.get("pid") or 0),
                        "name": str(row.get("name") or "")[:80],
                        "cmdline": str(row.get("cmdline") or "")[:240],
                        "port": int(row.get("port") or 0),
                    }
                    for row in remaining_after_launch[:8]
                ],
                **terminate_report,
            }
        probe_snapshot = self._collect_cdp_probe_snapshot(endpoint, timeout_seconds=0.5)
        _LOG.warning(
            "force_restart_to_cdp timeout endpoint=%s latency_ms=%s probe_reason=%s listeners=%s launch_pid=%s launch_alive=%s launch_exit_code=%s",
            endpoint,
            int((time.perf_counter() - started) * 1000),
            str(probe_snapshot.get("reason") or "unknown")[:120],
            int(probe_snapshot.get("listener_count") or 0),
            int((last_launch_meta or {}).get("pid") or 0),
            "1" if bool((last_launch_meta or {}).get("alive")) else "0",
            "" if (last_launch_meta or {}).get("exit_code") is None else str((last_launch_meta or {}).get("exit_code")),
        )
        return {
            "ok": False,
            "error": "cdp_launch_timeout",
            "endpoint": endpoint,
            "probe_reason": str(probe_snapshot.get("reason") or ""),
            "probe_listener_count": int(probe_snapshot.get("listener_count") or 0),
            "probe_listener_pids": list(probe_snapshot.get("listener_pids") or []),
            "launch_pid": int((last_launch_meta or {}).get("pid") or 0),
            "launch_alive": bool((last_launch_meta or {}).get("alive")),
            "launch_exit_code": (last_launch_meta or {}).get("exit_code"),
            **terminate_report,
        }
