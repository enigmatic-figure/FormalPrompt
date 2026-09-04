from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from formalprompt.models import CanvasDocument, WorkflowPort
from formalprompt.runtime import CanvasRuntime
from formalprompt.store import RunStore

ROOT = Path(__file__).parents[1]


def _chrome_path() -> str | None:
    names = ["google-chrome", "chromium", "chromium-browser"]
    for name in names:
        if found := shutil.which(name):
            return found
    if sys.platform == "win32":
        candidates = [
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
            Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def _unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_real_chrome_edit_validate_approve_compile_journey(tmp_path):
    chrome = _chrome_path()
    node = shutil.which("node")
    if not chrome or not node:
        pytest.skip("Chrome-family browser and Node are required for the browser smoke test")
    template = ROOT / "src" / "formalprompt" / "templates" / "formalprompt-self-hosting.json"
    document = CanvasDocument.model_validate_json(template.read_text(encoding="utf-8"))
    store = RunStore.create(tmp_path, document)
    runtime = CanvasRuntime(store, token="browser-smoke-token", renderer="none")
    runtime.start()
    try:
        assert runtime.wait_until_ready(timeout_seconds=5)
        environment = {
            **os.environ,
            "FORMALPROMPT_CANVAS_URL": runtime.canvas_url,
            "CHROME_PATH": chrome,
            "CHROME_DEBUG_PORT": str(_unused_port()),
        }
        completed = subprocess.run(
            [node, str(ROOT / "scripts" / "browser-smoke.mjs")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=30,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        journey = json.loads(completed.stdout)
        assert journey["initial"]["tabs"] == 4
        assert journey["initial"]["issues"] == 2
        assert "14 of 15" in journey["initial"]["coverage"]
        assert journey["final"] == {
            "revision": "Revision 1",
            "issues": 0,
            "status": "compiled",
            "hashCleared": True,
        }
        assert runtime.wait(timeout_seconds=5)
        assert (store.path / "result.json").is_file()
    finally:
        runtime.stop()


def test_real_chrome_workflow_graph_edit_journey(tmp_path):
    chrome = _chrome_path()
    node = shutil.which("node")
    if not chrome or not node:
        pytest.skip("Chrome-family browser and Node are required for the browser smoke test")
    template = ROOT / "src" / "formalprompt" / "templates" / "workflow-project.json"
    document = CanvasDocument.model_validate_json(template.read_text(encoding="utf-8"))
    implement = next(item for item in document.workflow.nodes if item.id == "implement")
    implement.input_ports.append(
        WorkflowPort(
            id="alternate",
            label="Alternate control",
            data_type="control",
        )
    )
    store = RunStore.create(tmp_path, document)
    runtime = CanvasRuntime(store, token="workflow-browser-smoke-token", renderer="none")
    runtime.start()
    try:
        assert runtime.wait_until_ready(timeout_seconds=5)
        environment = {
            **os.environ,
            "FORMALPROMPT_CANVAS_URL": runtime.canvas_url,
            "CHROME_PATH": chrome,
            "CHROME_DEBUG_PORT": str(_unused_port()),
        }
        completed = subprocess.run(
            [node, str(ROOT / "scripts" / "workflow-browser-smoke.mjs")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=30,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        journey = json.loads(completed.stdout)
        assert journey["initial"] == {
            "nodes": 6,
            "edges": 6,
            "title": "Validated implementation workflow",
            "revision": 0,
        }
        assert journey["added"] == {
            "provenance": "unresolved",
            "state": "unresolved · needs input",
        }
        assert journey["final"] == {
            "nodes": 7,
            "edges": 7,
            "connectedPort": True,
            "addedProvenance": "unresolved",
            "selectedTitle": "Implement verified project",
            "inspector": "Implement verified project",
            "revision": 3,
            "hashCleared": True,
        }
        saved = store.read_document().workflow
        assert next(item for item in saved.nodes if item.id == "implement").title == (
            "Implement verified project"
        )
    finally:
        runtime.stop()
