from __future__ import annotations

from app.services.pinchtab_client import PinchTabClient


def test_open_tab_accepts_real_pinchtab_tab_id(monkeypatch):
    client = PinchTabClient(open_tab_max_attempts=1)

    def fake_post(path: str, payload: dict[str, object], timeout: float = 15.0) -> dict[str, object]:
        assert path == "/instances/inst-1/tabs/open"
        assert payload == {"url": "https://example.com"}
        assert timeout == 15.0
        # Simulate a real Pinchtab response shape
        return {
            "payload": {
                "tabId": "BBC0E188236A80FA67D1E433B1E2A828",
                "title": "Example Domain",
                "url": "https://example.com/",
            }
        }

    monkeypatch.setattr(client, "_post", fake_post)

    result = client.open_tab(instance_id="inst-1", url="https://example.com")

    assert result == {
        "ok": True,
        "tab_id": "BBC0E188236A80FA67D1E433B1E2A828",
    }


def test_open_tab_retries_on_failure(monkeypatch):
    calls: list[dict[str, object]] = []

    client = PinchTabClient(open_tab_max_attempts=3, open_tab_retry_interval=0.0)

    def fake_post(path: str, payload: dict[str, object], timeout: float = 15.0) -> dict[str, object]:
        calls.append({"path": path, "payload": payload, "timeout": timeout})
        # First call fails, second succeeds.
        if len(calls) == 1:
            return {"ok": False, "error": "pinchtab_http_error:500"}
        return {
            "ok": True,
            "payload": {
                "tabId": "tab-1",
                "title": "Example Domain",
            },
        }

    monkeypatch.setattr(client, "_post", fake_post)

    result = client.open_tab(instance_id="inst-1", url="https://example.com")

    assert result == {"ok": True, "tab_id": "tab-1"}
    assert len(calls) == 2


def test_launch_instance_polls_until_running(monkeypatch):
    client = PinchTabClient(launch_max_attempts=5, launch_poll_interval=0.0)

    launch_calls: list[dict[str, object]] = []
    get_instance_calls: list[str] = []

    def fake_post(path: str, payload: dict[str, object], timeout: float = 15.0) -> dict[str, object]:
        launch_calls.append({"path": path, "payload": payload, "timeout": timeout})
        assert path == "/instances/launch"
        assert payload == {}
        return {
            "ok": True,
            "payload": {
                "id": "inst_ready",
                "status": "starting",
            },
        }

    def fake_get_instance(instance_id: str, timeout: float = 5.0) -> dict[str, object]:
        get_instance_calls.append(instance_id)
        assert instance_id == "inst_ready"
        # First two polls still starting, then running
        if len(get_instance_calls) < 3:
            return {"ok": True, "payload": {"id": instance_id, "status": "starting"}}
        return {"ok": True, "payload": {"id": instance_id, "status": "running"}}

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr(client, "_get_instance", fake_get_instance)

    result = client.launch_instance()

    assert result == {"ok": True, "instance_id": "inst_ready"}
    # We should have polled a few times for readiness.
    assert len(get_instance_calls) >= 3


def test_launch_instance_times_out_when_not_running(monkeypatch):
    client = PinchTabClient(launch_max_attempts=3, launch_poll_interval=0.0)

    def fake_post(path: str, payload: dict[str, object], timeout: float = 15.0) -> dict[str, object]:
        assert path == "/instances/launch"
        assert payload == {}
        return {
            "ok": True,
            "payload": {
                "id": "inst_slow",
                "status": "starting",
            },
        }

    def fake_get_instance(instance_id: str, timeout: float = 5.0) -> dict[str, object]:
        # Always starting, never running
        assert instance_id == "inst_slow"
        return {"ok": True, "payload": {"id": instance_id, "status": "starting"}}

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr(client, "_get_instance", fake_get_instance)

    result = client.launch_instance()

    assert result["ok"] is False
    assert result["error"] == "pinchtab_instance_not_ready"
    assert result["instance_id"] == "inst_slow"
