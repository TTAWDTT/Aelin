from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.settings import settings


class PinchTabClient:
    """
    Very small HTTP client for a local PinchTab service.

    This is a lightweight adapter for a local PinchTab service. It assumes
    a PinchTab server is listening on `pinchtab_base_url` (defaults to
    http://127.0.0.1:9867) and exposes a minimal subset of its API:

    - POST /instances/launch -> { \"id\": \"inst_...\" }
    - POST /instances/{id}/tabs/open { \"url\": \"...\" } -> { \"tabId\": \"tab_...\" }
    - GET  /tabs/{tab_id}/snapshot
    - GET  /tabs/{tab_id}/text
    - POST /tabs/{tab_id}/action { \"kind\": \"click\", \"ref\": \"...\" }
    """

    def __init__(
        self,
        *,
        launch_max_attempts: int = 10,
        launch_poll_interval: float = 1.0,
        open_tab_max_attempts: int = 3,
        open_tab_retry_interval: float = 0.5,
    ) -> None:
        base = settings.pinchtab_base_url or "http://127.0.0.1:9867"
        self._base = str(base).rstrip("/")
        # How many times to poll for instance readiness before giving up.
        self._launch_max_attempts = int(launch_max_attempts)
        self._launch_poll_interval = float(launch_poll_interval)
        # How many times to retry open_tab on transient failures.
        self._open_tab_max_attempts = int(open_tab_max_attempts)
        self._open_tab_retry_interval = float(open_tab_retry_interval)

    def runtime_status(self) -> dict[str, Any]:
        return {"base_url": self._base}

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def _get(self, path: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
        query = ""
        if params:
            query = "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(self._url(path) + query, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.URLError as exc:
            return {"ok": False, "error": f"pinchtab_http_error:{exc}"}
        try:
            payload = json.loads(data)
        except Exception:
            return {"ok": False, "error": "pinchtab_invalid_json"}
        return payload if isinstance(payload, dict) else {"ok": False, "error": "pinchtab_invalid_payload"}

    def _post(self, path: str, payload: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(path),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.URLError as exc:
            return {"ok": False, "error": f"pinchtab_http_error:{exc}"}
        try:
            payload = json.loads(data)
        except Exception:
            return {"ok": False, "error": "pinchtab_invalid_json"}
        return payload if isinstance(payload, dict) else {"ok": False, "error": "pinchtab_invalid_payload"}

    def _get_instance(self, instance_id: str, timeout: float = 5.0) -> dict[str, Any]:
        """
        Fetch a single instance object from Pinchtab.

        This is a thin wrapper around GET /instances/{id} so that callers can
        poll for readiness without duplicating HTTP details.
        """
        return self._get(f"/instances/{instance_id}", timeout=timeout)

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def launch_instance(self) -> dict[str, Any]:
        """
        Launch a new Pinchtab instance and wait until it is ready.

        Real Pinchtab returns an instance object with status \"starting\" first;
        the instance only accepts tab commands once status becomes \"running\".
        We hide this detail here by polling /instances/{id} for a short period
        so that callers can assume the instance is ready.
        """
        out = self._post("/instances/launch", {})
        if not isinstance(out, dict) or not out.get("ok", True):
            # If the low-level call failed, propagate its structure so callers
            # can see the underlying error.
            return out if isinstance(out, dict) else {"ok": False, "error": "pinchtab_launch_invalid_response"}
        payload = out.get("payload") if isinstance(out.get("payload"), dict) else out
        inst_id = str(payload.get("id") or "")
        if not inst_id:
            return {"ok": False, "error": "pinchtab_missing_instance_id", "raw": out}

        # Best-effort readiness wait: poll up to the configured number of
        # attempts for status == "running". If we never see "running", report
        # a clear error so the agent loop can decide what to do.
        last_status: Any = None
        for _ in range(self._launch_max_attempts):
            inst = self._get_instance(inst_id)
            if not isinstance(inst, dict) or not inst.get("ok", True):
                last_status = inst
                time.sleep(self._launch_poll_interval)
                continue
            inst_payload = inst.get("payload") if isinstance(inst.get("payload"), dict) else inst
            last_status = str(inst_payload.get("status") or "").strip().lower()
            if last_status == "running":
                return {"ok": True, "instance_id": inst_id}
            time.sleep(self._launch_poll_interval)

        return {
            "ok": False,
            "error": "pinchtab_instance_not_ready",
            "instance_id": inst_id,
            "last_status": last_status,
        }

    def open_tab(self, *, instance_id: str, url: str) -> dict[str, Any]:
        payload = {"url": url}
        last_error: dict[str, Any] | None = None
        for _ in range(self._open_tab_max_attempts):
            out = self._post(f"/instances/{instance_id}/tabs/open", payload)
            if isinstance(out, dict) and out.get("ok", True):
                # Accept both real Pinchtab-style `tabId` and older `id`.
                payload_obj = out.get("payload") if isinstance(out.get("payload"), dict) else out
                tab_id = str(payload_obj.get("tabId") or payload_obj.get("id") or "")
                if not tab_id:
                    return {"ok": False, "error": "pinchtab_missing_tab_id", "raw": out}
                return {"ok": True, "tab_id": tab_id}
            if isinstance(out, dict):
                last_error = out
            time.sleep(self._open_tab_retry_interval)

        if last_error is not None:
            return last_error
        return {"ok": False, "error": "pinchtab_open_tab_failed"}

    def snapshot(self, *, tab_id: str) -> dict[str, Any]:
        return self._get(f"/tabs/{tab_id}/snapshot")

    def text(self, *, tab_id: str, mode: str = "readable") -> dict[str, Any]:
        return self._get(f"/tabs/{tab_id}/text", params={"mode": mode})

    def action(self, *, tab_id: str, kind: str, ref: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": kind}
        if ref:
            payload["ref"] = ref
        payload.update(kwargs)
        return self._post(f"/tabs/{tab_id}/action", payload)


_pinchtab_client: PinchTabClient | None = None


def get_pinchtab_client() -> PinchTabClient:
    global _pinchtab_client
    if _pinchtab_client is None:
        _pinchtab_client = PinchTabClient()
    return _pinchtab_client
