from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from formalprompt.cli import app
from formalprompt.compiler import compile_run
from formalprompt.launchers import LauncherUnavailable
from formalprompt.store import RunStore
from tests.test_session_api import minimal_document

runner = CliRunner()


def test_validate_command_emits_machine_readable_readiness(tmp_path):
    document_path = tmp_path / "canvas.json"
    document_path.write_text(json.dumps(minimal_document()), encoding="utf-8")

    result = runner.invoke(app, ["validate", str(document_path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {"valid": True, "ready": True, "issues": []}


def test_validate_command_rejects_invalid_protocol_document(tmp_path):
    document_path = tmp_path / "bad.json"
    document_path.write_text('{"protocol":"wrong"}', encoding="utf-8")

    result = runner.invoke(app, ["validate", str(document_path), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["errors"]


def test_template_command_writes_a_structurally_valid_canvas(tmp_path):
    output = tmp_path / "software-project.json"

    result = runner.invoke(app, ["template", "software-project", str(output)])

    assert result.exit_code == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["protocol"] == "agent-canvas/v1"
    assert document["kind"] == "formalprompt/specification"
    assert len(document["tabs"]) >= 3


def test_minimal_and_self_hosting_templates_are_available(tmp_path):
    for name in ("minimal", "formalprompt-self-hosting"):
        output = tmp_path / f"{name}.json"
        result = runner.invoke(app, ["template", name, str(output)])
        assert result.exit_code == 0
        document = json.loads(output.read_text(encoding="utf-8"))
        assert document["protocol"] == "agent-canvas/v1"


def test_schema_command_writes_protocol_schema(tmp_path):
    output = tmp_path / "agent-canvas-v1.schema.json"

    result = runner.invoke(app, ["schema", str(output)])

    assert result.exit_code == 0
    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["title"] == "CanvasDocument"
    assert schema["additionalProperties"] is False


def test_open_command_creates_run_and_emits_ready_event(tmp_path, monkeypatch):
    document_path = tmp_path / "canvas.json"
    document_path.write_text(json.dumps(minimal_document()), encoding="utf-8")
    calls = []

    class FakeRuntime:
        def __init__(self, store, **options):
            self.store = store
            self.options = options
            self.port = 48123
            self.renderer = options["renderer"]
            self.canvas_url = "http://127.0.0.1:48123/#token=test"
            calls.append("created")

        def start(self):
            calls.append("started")

        def wait_until_ready(self, timeout_seconds=10):
            return True

        def open_renderer(self):
            calls.append("opened")

        def wait(self, timeout_seconds=None):
            calls.append("waited")
            return True

        def stop(self):
            calls.append("stopped")

    monkeypatch.setattr("formalprompt.cli.CanvasRuntime", FakeRuntime)
    runs = tmp_path / "runs"

    result = runner.invoke(
        app,
        [
            "open",
            str(document_path),
            "--runs-dir",
            str(runs),
            "--renderer",
            "none",
            "--json",
        ],
    )

    assert result.exit_code == 0
    event = json.loads(result.stdout.splitlines()[0])
    assert event["event"] == "ready"
    assert event["renderer"] == "none"
    assert event["url"].endswith("#token=test")
    assert (runs / event["run_id"] / "document.json").is_file()
    assert calls == ["created", "started", "opened", "waited", "stopped"]


def test_open_command_falls_back_to_url_only_when_renderer_fails(tmp_path, monkeypatch):
    document_path = tmp_path / "canvas.json"
    document_path.write_text(json.dumps(minimal_document()), encoding="utf-8")
    calls = []

    class FakeRuntime:
        def __init__(self, store, **options):
            self.store = store
            self.renderer = options["renderer"]
            self.canvas_url = "http://127.0.0.1:48123/#token=test"

        def start(self):
            calls.append("started")

        def wait_until_ready(self, timeout_seconds=10):
            return True

        def open_renderer(self):
            calls.append("open-failed")
            raise LauncherUnavailable("Carbonyl dependency check failed")

        def wait(self, timeout_seconds=None):
            calls.append("waited")
            return True

        def stop(self):
            calls.append("stopped")

    monkeypatch.setattr("formalprompt.cli.CanvasRuntime", FakeRuntime)

    result = runner.invoke(
        app,
        [
            "open",
            str(document_path),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--renderer",
            "carbonyl",
            "--json",
        ],
    )

    assert result.exit_code == 0
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert [event["event"] for event in events] == ["renderer-fallback", "ready"]
    assert events[0]["message"] == "Carbonyl dependency check failed"
    assert events[1]["renderer"] == "none"
    assert calls == ["started", "open-failed", "waited", "stopped"]


def test_open_command_emits_json_error_when_server_cannot_start(tmp_path, monkeypatch):
    document_path = tmp_path / "canvas.json"
    document_path.write_text(json.dumps(minimal_document()), encoding="utf-8")
    calls = []

    class FakeRuntime:
        def __init__(self, store, **options):
            self.store = store

        def start(self):
            raise RuntimeError("Unable to bind canvas server to 127.0.0.1:9000")

        def stop(self):
            calls.append("stopped")

    monkeypatch.setattr("formalprompt.cli.CanvasRuntime", FakeRuntime)

    result = runner.invoke(
        app,
        [
            "open",
            str(document_path),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--renderer",
            "none",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "contract": "agent-canvas-session/v1",
        "event": "error",
        "run_id": next((tmp_path / "runs").iterdir()).name,
        "message": "Unable to bind canvas server to 127.0.0.1:9000",
    }
    assert calls == ["stopped"]


def test_result_command_reads_persisted_completion(tmp_path):
    store = RunStore.create(tmp_path, minimal_document(), run_id="run-1")
    store.approve("CLI test", 0)
    expected = compile_run(store, 0)

    result = runner.invoke(app, ["result", str(store.path), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == expected


def test_result_command_rejects_an_unverified_result_file(tmp_path):
    run = tmp_path / "run-1"
    run.mkdir()
    (run / "result.json").write_text(
        json.dumps({"contract": "agent-canvas-result/v1", "status": "compiled"}),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["result", str(run), "--json"])

    assert result.exit_code == 1
    assert "no verified compiled result" in result.stderr


@pytest.mark.parametrize("interrupted", [False, True])
def test_resume_emits_terminal_completion_without_starting_server(
    tmp_path, monkeypatch, interrupted
):
    store = RunStore.create(tmp_path, minimal_document(), run_id="terminal-run")
    store.approve("CLI test", 0)
    if interrupted:
        original_mark_compiled = store.mark_compiled

        def interrupt_after_publication(revision):
            raise KeyboardInterrupt

        monkeypatch.setattr(store, "mark_compiled", interrupt_after_publication)
        with pytest.raises(KeyboardInterrupt):
            compile_run(store, 0)
        monkeypatch.setattr(store, "mark_compiled", original_mark_compiled)
    else:
        compile_run(store, 0)

    def fail_if_runtime_starts(*args, **kwargs):
        raise AssertionError("Terminal resume must not start a canvas server")

    monkeypatch.setattr("formalprompt.cli.CanvasRuntime", fail_if_runtime_starts)
    result = runner.invoke(app, ["resume", str(store.path), "--renderer", "none", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["event"] == "completed"
    assert payload["status"] == "compiled"
    assert store.read_state()["status"] == "compiled"
