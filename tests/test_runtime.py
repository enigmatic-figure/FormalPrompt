from __future__ import annotations

import json
import socket

import httpx
import pytest

from formalprompt.launchers import LauncherUnavailable
from formalprompt.runtime import CanvasRuntime
from formalprompt.store import RunStore
from tests.test_session_api import minimal_document


def test_runtime_serves_real_loopback_requests_and_stops_after_compilation(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    runtime = CanvasRuntime(
        store,
        token="runtime-token",
        host="127.0.0.1",
        port=0,
        renderer="none",
    )

    runtime.start()
    try:
        assert runtime.wait_until_ready(timeout_seconds=5)
        assert runtime.port > 0
        headers = {"Authorization": "Bearer runtime-token"}
        session = httpx.get(f"{runtime.base_url}/api/session", headers=headers)
        approval = httpx.post(
            f"{runtime.base_url}/api/approve",
            headers=headers,
            json={"approved_by": "Runtime test", "expected_revision": 0},
        )
        compilation = httpx.post(
            f"{runtime.base_url}/api/compile",
            headers=headers,
            json={"expected_revision": 0},
        )

        assert session.status_code == 200
        assert approval.status_code == 200
        assert compilation.status_code == 200
        assert runtime.wait(timeout_seconds=5)
        result = json.loads((store.path / "result.json").read_text(encoding="utf-8"))
        assert result["status"] == "compiled"
    finally:
        runtime.stop()


def test_runtime_owns_and_terminates_carbonyl_process(tmp_path, monkeypatch):
    store = RunStore.create(tmp_path, minimal_document())
    calls = []

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminated")

        def wait(self, timeout=None):
            calls.append(("waited", timeout))
            return 0

        def kill(self):
            calls.append("killed")

    process = FakeProcess()

    def fake_launch(renderer, url, **options):
        calls.append((renderer, url, options))
        return process

    monkeypatch.setattr("formalprompt.runtime.launch", fake_launch)
    runtime = CanvasRuntime(store, token="token", renderer="carbonyl")

    runtime.open_renderer()
    runtime.stop()

    assert calls[0][0] == "carbonyl"
    assert calls[0][2].get("wait") is not True
    assert "terminated" in calls
    assert ("waited", 5) in calls


def test_runtime_wraps_bind_failure_with_address_and_port(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen(1)
    port = occupied.getsockname()[1]
    runtime = CanvasRuntime(store, token="token", host="127.0.0.1", port=port)

    try:
        with pytest.raises(RuntimeError, match=rf"127\.0\.0\.1:{port}.*--port 0"):
            runtime.start()
    finally:
        occupied.close()
        runtime.stop()


def test_runtime_reports_carbonyl_that_exits_during_startup(tmp_path, monkeypatch):
    store = RunStore.create(tmp_path, minimal_document())

    class ExitedProcess:
        def poll(self):
            return 127

    monkeypatch.setattr("formalprompt.runtime.launch", lambda renderer, url: ExitedProcess())
    runtime = CanvasRuntime(store, token="token", renderer="carbonyl")

    with pytest.raises(LauncherUnavailable, match="status 127"):
        runtime.open_renderer()
