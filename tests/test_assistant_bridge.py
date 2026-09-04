from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress

import pytest
from fastapi.testclient import TestClient

from formalprompt.assistant import AssistantProtocolError, CommandAssistant
from formalprompt.server import create_app
from formalprompt.store import RunStore
from tests.test_session_api import minimal_document


def test_command_assistant_uses_json_contract_and_returns_scoped_response(tmp_path):
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        """import json, sys
request = json.load(sys.stdin)
json.dump({
    'contract': 'agent-canvas-assistant/v1',
    'request_id': request['request_id'],
    'summary': 'Use the portable option.',
    'suggestions': [{'value': 'portable', 'label': 'Portable', 'implications': 'Runs anywhere.'}],
    'questions': []
}, sys.stdout)
""",
        encoding="utf-8",
    )
    assistant = CommandAssistant([sys.executable, str(adapter)])
    request = {
        "contract": "agent-canvas-assistant/v1",
        "request_id": "request-1",
        "operation": "field-assistance",
        "context": {"field": {"id": "runtime.mode"}, "question": "Which option?"},
    }

    response = assistant.invoke(request)

    assert response.request_id == "request-1"
    assert response.summary == "Use the portable option."
    assert response.suggestions[0].value == "portable"


def test_command_assistant_rejects_non_protocol_output(tmp_path):
    adapter = tmp_path / "bad-adapter.py"
    adapter.write_text("print('not json')\n", encoding="utf-8")

    with pytest.raises(AssistantProtocolError, match="valid JSON"):
        CommandAssistant([sys.executable, str(adapter)]).invoke(
            {
                "contract": "agent-canvas-assistant/v1",
                "request_id": "request-2",
                "operation": "field-assistance",
                "context": {},
            }
        )


def test_command_assistant_stops_before_streams_can_exceed_memory_limit(tmp_path):
    adapter = tmp_path / "flood-adapter.py"
    adapter.write_text(
        "import os\nos.write(1, b'x' * 5_000_000)\nos.write(2, b'y' * 5_000_000)\n",
        encoding="utf-8",
    )

    with pytest.raises(AssistantProtocolError, match="exceeded the configured size limit"):
        CommandAssistant(
            [sys.executable, str(adapter)],
            maximum_output_bytes=1024,
            maximum_error_bytes=1024,
        ).invoke(
            {
                "contract": "agent-canvas-assistant/v1",
                "request_id": "request-flood",
                "operation": "field-assistance",
                "context": {},
            }
        )


@pytest.mark.parametrize("failure_mode", ["timeout", "overflow"])
def test_command_assistant_terminates_descendant_processes(tmp_path, failure_mode):
    pid_file = tmp_path / "grandchild.pid"
    adapter = tmp_path / f"{failure_mode}-tree-adapter.py"
    overflow = "os.write(1, b'x' * 5_000_000)" if failure_mode == "overflow" else ""
    detached = ", start_new_session=True" if os.name != "nt" else ""
    adapter.write_text(
        f"""import os, pathlib, subprocess, time
child = subprocess.Popen([{sys.executable!r}, '-c', 'import time; time.sleep(30)']{detached})
pathlib.Path({str(pid_file)!r}).write_text(str(child.pid), encoding='utf-8')
{overflow}
time.sleep(30)
""",
        encoding="utf-8",
    )
    assistant = CommandAssistant(
        [sys.executable, str(adapter)],
        timeout_seconds=0.5 if failure_mode == "timeout" else 5,
        maximum_output_bytes=1024,
    )
    expected = "failed to run" if failure_mode == "timeout" else "exceeded"

    try:
        with pytest.raises(AssistantProtocolError, match=expected):
            assistant.invoke(
                {
                    "contract": "agent-canvas-assistant/v1",
                    "request_id": f"request-{failure_mode}-tree",
                    "operation": "field-assistance",
                    "context": {},
                }
            )
        deadline = time.monotonic() + 3
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pid_file.is_file()
        grandchild_pid = int(pid_file.read_text(encoding="utf-8"))
        while _pid_is_running(grandchild_pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not _pid_is_running(grandchild_pid)
    finally:
        if pid_file.is_file():
            _force_kill(int(pid_file.read_text(encoding="utf-8")))


def _pid_is_running(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _force_kill(pid: int) -> None:
    if not _pid_is_running(pid):
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    with suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


def test_enabled_field_assistance_is_queued_without_a_backend(tmp_path):
    document = minimal_document()
    field = document["tabs"][0]["sections"][0]["fields"][0]
    field["assistance"] = {"enabled": True, "prompt": "Help refine the project goal"}
    store = RunStore.create(tmp_path, document)
    client = TestClient(create_app(store, token="token"))

    response = client.post(
        "/api/assistance",
        headers={"Authorization": "Bearer token"},
        json={"field_id": "project.goal", "question": "Show two sharper alternatives"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pending"
    request_path = store.path / "requests" / f"{payload['request_id']}.json"
    saved = json.loads(request_path.read_text(encoding="utf-8"))
    assert saved["context"]["field"]["id"] == "project.goal"
    assert saved["context"]["question"] == "Show two sharper alternatives"
    assert "tabs" not in saved["context"]


def test_assistant_failure_is_durably_recorded(tmp_path):
    document = minimal_document()
    field = document["tabs"][0]["sections"][0]["fields"][0]
    field["assistance"] = {"enabled": True, "prompt": "Help"}
    adapter = tmp_path / "bad-adapter.py"
    adapter.write_text("print('not json')\n", encoding="utf-8")
    store = RunStore.create(tmp_path / "runs", document)
    client = TestClient(
        create_app(store, token="token", assistant=CommandAssistant([sys.executable, str(adapter)]))
    )

    response = client.post(
        "/api/assistance",
        headers={"Authorization": "Bearer token"},
        json={"field_id": "project.goal", "question": "Help"},
    )

    assert response.status_code == 502
    failure_files = list((store.path / "failures").glob("*.json"))
    assert len(failure_files) == 1
    failure = json.loads(failure_files[0].read_text(encoding="utf-8"))
    assert failure["operation"] == "field-assistance"
    assert failure["error_type"] == "AssistantProtocolError"
    assert '"type":"assistance.failed"' in (store.path / "events.jsonl").read_text(encoding="utf-8")
