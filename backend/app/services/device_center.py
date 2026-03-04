from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.schemas import AelinDeviceProcessItem
from app.settings import settings

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None

PSUTIL_AVAILABLE = psutil is not None


class DeviceScreenCaptureError(RuntimeError):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(str(detail or "device_screen_capture_error"))
        self.status_code = max(400, int(status_code or 500))
        self.detail = str(detail or "device_screen_capture_error")[:220]


def _desktop_plugin_headers() -> dict[str, str]:
    token = str(getattr(settings, "desktop_plugin_token", "") or "").strip()
    if not token:
        return {}
    return {"x-aelin-token": token}


def _desktop_plugin_error_detail(resp: httpx.Response) -> str:
    text = ""
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        text = str(payload.get("detail") or payload.get("message") or "").strip()
    if not text:
        text = str(resp.text or "").strip()
    if not text:
        text = f"status={resp.status_code}"
    return text[:180]


def capture_device_screen(
    *,
    display_id: str = "",
    max_edge: int = 1280,
    image_format: str = "jpeg",
    quality: int = 72,
) -> dict[str, Any]:
    base_url = str(getattr(settings, "desktop_plugin_base_url", "") or "").strip().rstrip("/")
    if not base_url:
        raise DeviceScreenCaptureError(status_code=503, detail="desktop_plugin_unconfigured")

    timeout_s = max(2.0, float(getattr(settings, "desktop_plugin_timeout_seconds", 12.0) or 12.0))
    payload: dict[str, Any] = {
        "max_edge": max(640, min(4096, int(max_edge or 1280))),
        "format": "png" if str(image_format or "").strip().lower() == "png" else "jpeg",
    }
    if payload["format"] == "jpeg":
        payload["quality"] = max(35, min(95, int(quality or 72)))
    display_clean = str(display_id or "").strip()[:64]
    if display_clean:
        payload["display_id"] = display_clean

    url = f"{base_url}/v1/device/screen/capture"
    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
            resp = client.post(url, json=payload, headers=_desktop_plugin_headers())
    except Exception as exc:
        raise DeviceScreenCaptureError(
            status_code=503,
            detail=f"desktop_plugin_unreachable: {str(exc)[:180]}",
        ) from exc

    if int(resp.status_code) >= 400:
        raise DeviceScreenCaptureError(
            status_code=502,
            detail=f"desktop_plugin_capture_failed: {_desktop_plugin_error_detail(resp)}",
        )

    try:
        raw = resp.json()
    except Exception as exc:
        raise DeviceScreenCaptureError(status_code=502, detail="desktop_plugin_invalid_json") from exc
    if not isinstance(raw, dict):
        raise DeviceScreenCaptureError(status_code=502, detail="desktop_plugin_invalid_payload")

    data_url = str(raw.get("data_url") or "").strip()
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise DeviceScreenCaptureError(status_code=502, detail="desktop_plugin_invalid_image_payload")
    max_data_len = max(
        200_000,
        int(getattr(settings, "desktop_plugin_capture_max_data_url_length", 3_000_000) or 3_000_000),
    )
    if len(data_url) > max_data_len:
        raise DeviceScreenCaptureError(
            status_code=502,
            detail=f"desktop_plugin_image_too_large: {len(data_url)}",
        )

    try:
        width = max(0, int(raw.get("width") or 0))
    except Exception:
        width = 0
    try:
        height = max(0, int(raw.get("height") or 0))
    except Exception:
        height = 0

    return {
        "data_url": data_url,
        "name": str(raw.get("name") or "").strip()[:120],
        "width": width,
        "height": height,
        "source_display": str(raw.get("source_display") or "").strip()[:64],
        "captured_at": str(raw.get("captured_at") or datetime.now(timezone.utc).isoformat())[:64],
    }


def device_is_windows() -> bool:
    return platform.system().strip().lower().startswith("win")


def device_capabilities() -> tuple[str, dict[str, bool], list[str]]:
    platform_name = platform.system().strip().lower() or "unknown"
    is_windows = device_is_windows()
    has_psutil = psutil is not None
    has_windows_fallback = bool(is_windows)
    process_list_supported = bool(has_psutil or has_windows_fallback)
    capabilities = {
        "process_list": process_list_supported,
        "process_terminate": bool(has_psutil or has_windows_fallback),
        "process_priority": bool(has_psutil or has_windows_fallback),
        "mode_focus": bool(is_windows),
        "mode_silent": bool(is_windows),
        "mode_normal": True,
        "optimize_processes": process_list_supported,
    }
    notes: list[str] = []
    if not has_psutil:
        if is_windows:
            notes.append("psutil unavailable; using Windows fallback process probe (cpu may be approximate)")
        else:
            notes.append("psutil unavailable; process controls disabled")
    if not is_windows:
        notes.append("non-windows runtime: mode actions may degrade to state-only updates")
    return platform_name, capabilities, notes


def normalize_device_mode(raw: str) -> str:
    mode = str(raw or "").strip().lower()
    alias = {
        "meeting": "meeting",
        "focus": "focus",
        "sleep": "sleep",
        "normal": "normal",
        "default": "normal",
        "开会": "meeting",
        "专注": "focus",
        "睡眠": "sleep",
        "恢复": "normal",
    }
    return alias.get(mode, "normal")


def run_powershell(script: str, *, timeout_s: int = 8) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_s)),
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as exc:
        return False, str(exc)
    output = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode == 0, output


def set_windows_toast_enabled(enabled: bool) -> tuple[bool, str]:
    value = "1" if enabled else "0"
    script = (
        "New-Item -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\PushNotifications' "
        "-Force | Out-Null; "
        f"Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\PushNotifications' "
        f"-Name ToastEnabled -Type DWord -Value {value}; "
        "Write-Output 'ok'"
    )
    ok, detail = run_powershell(script)
    return ok, detail or ("ok" if ok else "failed")


def set_windows_brightness(percent: int) -> tuple[bool, str]:
    safe = max(10, min(100, int(percent or 35)))
    script = (
        "$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue; "
        f"if ($m) {{ $null = $m.WmiSetBrightness(1,{safe}); Write-Output 'ok'; }} "
        "else { Write-Output 'unsupported'; exit 1; }"
    )
    ok, detail = run_powershell(script)
    return ok, detail or ("ok" if ok else "brightness unsupported")


def get_process_name_by_pid_windows(pid: int) -> str:
    safe_pid = max(1, int(pid or 0))
    script = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$p = Get-Process -Id {safe_pid}; "
        "if ($null -eq $p) { Write-Output ''; exit 1; } "
        "Write-Output $p.ProcessName"
    )
    ok, detail = run_powershell(script, timeout_s=4)
    if not ok:
        return ""
    return str(detail or "").strip().lower()


def collect_device_process_items_windows_fallback(*, sort_by: str, limit: int) -> list[AelinDeviceProcessItem]:
    max_items = max(1, min(200, int(limit or 40)))
    sort_key = "memory" if str(sort_by or "").strip().lower() == "memory" else "cpu"
    script = (
        "$ErrorActionPreference='SilentlyContinue'; "
        "Get-Process | Select-Object Name,Id,WorkingSet64,CPU,StartTime,PriorityClass,ProcessName "
        "| ConvertTo-Json -Compress"
    )
    ok, detail = run_powershell(script, timeout_s=12)
    if not ok or not detail:
        return []

    try:
        parsed = json.loads(detail)
    except Exception:
        return []

    rows_data: list[dict[str, Any]]
    if isinstance(parsed, list):
        rows_data = [x for x in parsed if isinstance(x, dict)]
    elif isinstance(parsed, dict):
        rows_data = [parsed]
    else:
        return []

    critical_names = {
        "system",
        "idle",
        "registry",
        "csrss",
        "wininit",
        "services",
        "lsass",
        "svchost",
        "explorer",
    }

    rows: list[AelinDeviceProcessItem] = []
    for item in rows_data:
        try:
            pid = int(item.get("Id") or 0)
        except Exception:
            continue
        if pid <= 0:
            continue
        name_raw = str(item.get("Name") or item.get("ProcessName") or f"pid-{pid}").strip()
        name = f"{name_raw}.exe" if name_raw and "." not in name_raw else name_raw
        ws = float(item.get("WorkingSet64") or 0)
        memory_mb = max(0.0, ws / (1024 * 1024))
        cpu_seconds = 0.0
        try:
            cpu_seconds = float(item.get("CPU") or 0.0)
        except Exception:
            cpu_seconds = 0.0
        status = "running"
        created_iso: str | None = None
        start_raw = item.get("StartTime")
        if isinstance(start_raw, str) and start_raw.strip():
            created_iso = start_raw.strip()

        reasons: list[str] = []
        score = 0.0
        if memory_mb >= 1400:
            reasons.append("内存占用过高")
            score += 2.5
        elif memory_mb >= 800:
            reasons.append("内存占用偏高")
            score += 1.2
        if cpu_seconds >= 1200:
            reasons.append("CPU累计时间较高")
            score += 0.8

        lower = name.lower().replace(".exe", "")
        safe_to_terminate = (lower not in critical_names) and (pid > 120)
        rows.append(
            AelinDeviceProcessItem(
                pid=pid,
                name=name,
                cpu_percent=0.0,
                memory_mb=round(memory_mb, 1),
                status=status,
                username="",
                create_time=created_iso,
                anomaly_score=round(score, 2),
                anomaly_reasons=reasons[:3],
                safe_to_terminate=safe_to_terminate,
            )
        )

    if sort_key == "memory":
        rows.sort(key=lambda x: (x.anomaly_score, x.memory_mb, x.pid), reverse=True)
    else:
        rows.sort(key=lambda x: (x.anomaly_score, x.memory_mb, x.pid), reverse=True)
    return rows[:max_items]


def set_process_priority(pid: int, level: str) -> tuple[bool, str]:
    target = str(level or "").strip().lower()

    if psutil is not None:
        try:
            proc = psutil.Process(int(pid))
            if device_is_windows():
                if target == "high":
                    proc.nice(psutil.HIGH_PRIORITY_CLASS)
                else:
                    proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            else:
                proc.nice(-5 if target == "high" else 10)
            return True, f"priority set to {target or 'low'}"
        except Exception:
            pass

    if device_is_windows():
        ps_level = "High" if target == "high" else "BelowNormal"
        script = (
            "$ErrorActionPreference='Stop'; "
            f"$p = Get-Process -Id {int(pid)}; "
            "if ($null -eq $p) { throw 'process not found'; } "
            f"$p.PriorityClass = '{ps_level}'; "
            "Write-Output 'ok'"
        )
        ok, detail = run_powershell(script, timeout_s=6)
        if ok:
            return True, f"priority set to {target or 'low'}"
        return False, detail or "failed to set process priority"

    return False, "process priority control unavailable"


def collect_device_process_items(*, sort_by: str, limit: int) -> list[AelinDeviceProcessItem]:
    if psutil is None:
        if device_is_windows():
            return collect_device_process_items_windows_fallback(sort_by=sort_by, limit=limit)
        return []

    max_items = max(1, min(200, int(limit or 40)))
    logical_cpus = 1
    try:
        logical_cpus = max(1, int(psutil.cpu_count(logical=True) or 1))
    except Exception:
        logical_cpus = 1
    sort_key = "memory" if str(sort_by or "").strip().lower() == "memory" else "cpu"
    current_user = str(os.environ.get("USERNAME") or os.environ.get("USER") or "").strip().lower()
    critical_names = {
        "system",
        "idle",
        "registry",
        "csrss.exe",
        "wininit.exe",
        "services.exe",
        "lsass.exe",
        "svchost.exe",
        "explorer.exe",
    }

    procs: list[Any] = []
    for proc in psutil.process_iter(attrs=["pid", "name", "username", "status", "memory_info", "create_time"]):
        try:
            proc.cpu_percent(None)
            procs.append(proc)
        except Exception:
            continue
    time.sleep(0.12)

    rows: list[AelinDeviceProcessItem] = []
    for proc in procs:
        try:
            with proc.oneshot():
                pid = int(proc.pid)
                name = str(proc.info.get("name") or proc.name() or f"pid-{pid}").strip()
                username = str(proc.info.get("username") or "").strip()
                status = str(proc.info.get("status") or proc.status() or "").strip().lower()
                raw_cpu = float(proc.cpu_percent(None) or 0.0)
                cpu = max(0.0, min(100.0, raw_cpu / logical_cpus))
                mem = proc.info.get("memory_info") or proc.memory_info()
                memory_mb = float(getattr(mem, "rss", 0) / (1024 * 1024))
                created = proc.info.get("create_time") or proc.create_time()
                created_iso = datetime.fromtimestamp(float(created), tz=timezone.utc).isoformat() if created else None
        except Exception:
            continue
        reasons: list[str] = []
        score = 0.0
        if cpu >= 80:
            reasons.append("CPU 持续高占用")
            score += 2.8
        elif cpu >= 55:
            reasons.append("CPU 偏高")
            score += 1.5
        if memory_mb >= 1400:
            reasons.append("内存占用过高")
            score += 2.5
        elif memory_mb >= 800:
            reasons.append("内存占用偏高")
            score += 1.2
        if status in {"zombie", "stopped"}:
            reasons.append(f"进程状态异常: {status}")
            score += 1.8

        name_lower = name.lower()
        user_match = bool(current_user and current_user in username.lower())
        safe_to_terminate = (name_lower not in critical_names) and ((user_match and pid > 120) or (pid > 5000))
        rows.append(
            AelinDeviceProcessItem(
                pid=pid,
                name=name,
                cpu_percent=round(cpu, 2),
                memory_mb=round(memory_mb, 1),
                status=status,
                username=username,
                create_time=created_iso,
                anomaly_score=round(score, 2),
                anomaly_reasons=reasons[:3],
                safe_to_terminate=safe_to_terminate,
            )
        )

    if sort_key == "memory":
        rows.sort(key=lambda x: (x.anomaly_score, x.memory_mb, x.cpu_percent), reverse=True)
    else:
        rows.sort(key=lambda x: (x.anomaly_score, x.cpu_percent, x.memory_mb), reverse=True)
    return rows[:max_items]


def apply_device_mode(mode: str) -> tuple[str, str, str, list[str], list[str]]:
    mode_norm = normalize_device_mode(mode)
    steps: list[str] = []
    warnings: list[str] = []

    if not device_is_windows():
        warnings.append("当前仅在 Windows 提供系统级模式控制，其它系统将只记录模式状态。")
        return mode_norm, "partial", f"模式已切换为 {mode_norm}（系统控制受限）", steps, warnings

    if mode_norm in {"meeting", "focus", "sleep"}:
        ok_toast, detail_toast = set_windows_toast_enabled(False)
        if ok_toast:
            steps.append("已限制系统通知横幅（Toast）。")
        else:
            warnings.append(f"限制系统通知失败: {detail_toast}")
    else:
        ok_toast, detail_toast = set_windows_toast_enabled(True)
        if ok_toast:
            steps.append("已恢复系统通知横幅。")
        else:
            warnings.append(f"恢复系统通知失败: {detail_toast}")

    if mode_norm == "focus":
        wechat_hits = 0
        if psutil is not None:
            for proc in psutil.process_iter(attrs=["pid", "name"]):
                try:
                    name = str(proc.info.get("name") or "").lower()
                    if "wechat" not in name:
                        continue
                    ok, detail = set_process_priority(int(proc.pid), "low")
                    if ok:
                        wechat_hits += 1
                    else:
                        warnings.append(f"WeChat 优先级调整失败: {detail}")
                except Exception:
                    continue
        if wechat_hits > 0:
            steps.append(f"已降低 {wechat_hits} 个 WeChat 进程优先级（减少打扰）。")
        else:
            warnings.append("未检测到 WeChat 进程，微信提示音需手动在系统混音器中关闭。")

    if mode_norm == "sleep":
        ok_brightness, detail_brightness = set_windows_brightness(35)
        if ok_brightness:
            steps.append("已尝试降低屏幕亮度至 35%。")
        else:
            warnings.append(f"亮度调整失败或设备不支持: {detail_brightness}")

    if mode_norm == "meeting":
        warnings.append("系统静音开关在部分设备上需手动确认（已保留开会模式状态）。")

    status = "applied" if not warnings else "partial"
    summary = (
        f"{mode_norm} 模式已应用。"
        if status == "applied"
        else f"{mode_norm} 模式已部分应用，请查看警告项。"
    )
    return mode_norm, status, summary, steps, warnings
