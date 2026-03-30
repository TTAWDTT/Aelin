from __future__ import annotations

import json

import app.services.device.device_center as device_center
from app.settings import settings
from tests.aelin_test_utils import _auth_headers, _create_test_client

def test_device_capabilities_endpoint_contract():
    client = _create_test_client()
    headers = _auth_headers(client)

    resp = client.get("/api/v1/aelin/device/capabilities", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("platform"), str)
    caps = data.get("capabilities") or {}
    for key in [
        "desktop_plugin_configured",
        "desktop_open_url",
        "desktop_activate_module",
        "desktop_execute_command",
    ]:
        assert key in caps

def test_device_screen_capture_proxy_success(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(settings, "desktop_plugin_base_url", "http://127.0.0.1:21914")
    monkeypatch.setattr(settings, "desktop_plugin_token", "plugin-token")
    monkeypatch.setattr(settings, "desktop_plugin_timeout_seconds", 8.0)
    monkeypatch.setattr(settings, "desktop_plugin_capture_max_data_url_length", 3_000_000)

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.text = ""

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "data_url": "data:image/jpeg;base64,QUJDRA==",
                "name": "screen-demo.jpg",
                "width": 1280,
                "height": 720,
                "source_display": "1",
                "captured_at": "2026-03-03T09:00:00Z",
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = args, kwargs

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            _ = exc_type, exc, tb
            return None

        def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
            assert url == "http://127.0.0.1:21914/v1/device/screen/capture"
            assert int(json.get("max_edge") or 0) == 1280
            assert str(json.get("format") or "") == "jpeg"
            assert int(json.get("quality") or 0) == 72
            assert str(json.get("mode") or "") == "fullscreen"
            assert bool(json.get("exclude_aelin_windows")) is True
            assert "selection_timeout_ms" not in json
            assert headers.get("x-aelin-token") == "plugin-token"
            return _FakeResponse()

    monkeypatch.setattr(device_center.httpx, "Client", _FakeClient)

    resp = client.post("/api/v1/aelin/device/screen/capture", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("data_url", "").startswith("data:image/jpeg;base64,")
    assert data.get("name") == "screen-demo.jpg"
    assert data.get("width") == 1280
    assert data.get("height") == 720
    assert data.get("source_display") == "1"

def test_device_screen_capture_proxy_unreachable_returns_503(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(settings, "desktop_plugin_base_url", "http://127.0.0.1:21914")
    monkeypatch.setattr(settings, "desktop_plugin_token", "")

    class _FailingClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = args, kwargs

        def __enter__(self) -> "_FailingClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            _ = exc_type, exc, tb
            return None

        def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
            _ = url, json, headers
            raise RuntimeError("connect_refused")

    monkeypatch.setattr(device_center.httpx, "Client", _FailingClient)

    resp = client.post("/api/v1/aelin/device/screen/capture", headers=headers)
    assert resp.status_code == 503, resp.text
    assert "desktop_plugin_unreachable" in str(resp.json().get("detail") or "")

def test_device_screen_capture_proxy_region_mode_payload_and_timeout(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(settings, "desktop_plugin_base_url", "http://127.0.0.1:21914")
    monkeypatch.setattr(settings, "desktop_plugin_token", "plugin-token")
    monkeypatch.setattr(settings, "desktop_plugin_timeout_seconds", 8.0)

    captured_timeout: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.text = ""

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "data_url": "data:image/png;base64,QUJDRA==",
                "name": "screen-region.png",
                "width": 640,
                "height": 360,
                "source_display": "custom-region",
                "captured_at": "2026-03-03T10:00:00Z",
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = args
            captured_timeout["timeout"] = kwargs.get("timeout")

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            _ = exc_type, exc, tb
            return None

        def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
            assert url == "http://127.0.0.1:21914/v1/device/screen/capture"
            assert str(json.get("mode") or "") == "region"
            assert bool(json.get("exclude_aelin_windows")) is False
            assert int(json.get("selection_timeout_ms") or 0) == 90_000
            assert headers.get("x-aelin-token") == "plugin-token"
            return _FakeResponse()

    monkeypatch.setattr(device_center.httpx, "Client", _FakeClient)

    resp = client.post(
        "/api/v1/aelin/device/screen/capture",
        json={"mode": "region", "selection_timeout_ms": 90_000},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert float(captured_timeout.get("timeout") or 0.0) >= 98.0


def test_desktop_plugin_health_bypasses_proxy_env(monkeypatch):
    monkeypatch.setattr(settings, "desktop_plugin_base_url", "http://127.0.0.1:21914")
    monkeypatch.setattr(settings, "desktop_plugin_timeout_seconds", 8.0)

    captured: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = args
            captured["trust_env"] = kwargs.get("trust_env")
            captured["follow_redirects"] = kwargs.get("follow_redirects")
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            _ = exc_type, exc, tb
            return None

        def get(self, url: str, headers: dict[str, str]):
            captured["url"] = url
            captured["headers"] = headers
            return _FakeResponse()

    monkeypatch.setattr(device_center.httpx, "Client", _FakeClient)

    assert device_center.desktop_plugin_health() is True
    assert captured["trust_env"] is False
    assert captured["follow_redirects"] is False
    assert captured["url"] == "http://127.0.0.1:21914/healthz"


def test_execute_desktop_command_proxy_success(monkeypatch):
    monkeypatch.setattr(settings, "desktop_plugin_base_url", "http://127.0.0.1:21914")
    monkeypatch.setattr(settings, "desktop_plugin_token", "plugin-token")
    monkeypatch.setattr(settings, "desktop_plugin_execute_enabled", True)
    monkeypatch.setattr(settings, "desktop_plugin_execute_timeout_seconds", 20.0)
    monkeypatch.setattr(settings, "desktop_plugin_execute_max_output_chars", 120)

    captured: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.text = ""

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "cwd": "D:/Github/Aelin/backend",
                "exit_code": 0,
                "stdout": "ok",
                "stderr": "",
                "timed_out": False,
                "summary": "command succeeded with exit code 0",
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = args
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            _ = exc_type, exc, tb
            return None

        def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResponse()

    monkeypatch.setattr(device_center.httpx, "Client", _FakeClient)

    result = device_center.execute_desktop_command(
        command="pytest -q",
        cwd="D:/Github/Aelin/backend",
        timeout_ms=15_000,
    )

    assert captured["url"] == "http://127.0.0.1:21914/v1/desktop/command/execute"
    assert captured["json"] == {
        "command": "pytest -q",
        "cwd": "D:/Github/Aelin/backend",
        "timeout_ms": 15_000,
    }
    assert captured["headers"] == {"x-aelin-token": "plugin-token"}
    assert float(captured["timeout"] or 0.0) >= 18.0
    assert result["exit_code"] == 0
    assert result["stdout"] == "ok"


