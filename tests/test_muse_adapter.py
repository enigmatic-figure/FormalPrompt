from __future__ import annotations

import json
from pathlib import Path

import pytest

from formalprompt.adapters.muse_runner import (
    MAX_PROMPT_BYTES,
    MuseRunnerAdapterError,
    _muse_prompt,
    invoke_muse,
)
from formalprompt.assistant import AssistantRequest, BoundedCommandResult


def test_muse_adapter_launches_fresh_read_only_schema_constrained_job(tmp_path, monkeypatch):
    runner = tmp_path / "muse_agent.py"
    runner.write_text("# runner placeholder\n", encoding="utf-8")
    repo = tmp_path / "project"
    repo.mkdir()
    result = tmp_path / "result.md"
    observed = {}

    def fake_run(command, stdin_text, **options):
        observed["command"] = command
        observed["stdin_text"] = stdin_text
        observed["options"] = options
        prompt_path = command[command.index("--prompt-file") + 1]
        observed["prompt"] = Path(prompt_path).read_text(encoding="utf-8")
        request_id = "compose-1"
        result.write_text(
            json.dumps(
                {
                    "contract": "agent-canvas-assistant/v1",
                    "request_id": request_id,
                    "summary": "A clarification canvas is needed.",
                    "suggestions": [],
                    "questions": ["Which deployment target is authoritative?"],
                    "disposition": "needs-clarification",
                    "next_document": None,
                }
            ),
            encoding="utf-8",
        )
        return BoundedCommandResult(
            returncode=0, stdout=f"Muse job completed; result: {result}\n", stderr=""
        )

    monkeypatch.setenv("FORMALPROMPT_MUSE_RUNNER", str(runner))
    monkeypatch.setenv("FORMALPROMPT_MUSE_REPO", str(repo))
    monkeypatch.setenv("FORMALPROMPT_MUSE_TIMEOUT", "45")
    monkeypatch.setattr("formalprompt.adapters.muse_runner.run_bounded_command", fake_run)
    request = AssistantRequest.model_validate(
        {
            "contract": "agent-canvas-assistant/v1",
            "request_id": "compose-1",
            "operation": "initialization-compose",
            "context": {"document": {}, "revision": 2},
        }
    )

    response = invoke_muse(request)

    assert response.disposition == "needs-clarification"
    assert observed["command"][2:4] == ["run", "--repo"]
    assert "--sandbox" in observed["command"]
    assert observed["command"][observed["command"].index("--sandbox") + 1] == "read-only"
    assert "--output-schema" in observed["command"]
    assert observed["options"]["timeout_seconds"] == 75
    assert observed["options"]["maximum_stdout_bytes"] == 262_144
    assert "FormalPrompt Muse operating contract" in observed["prompt"]
    assert "## Available seed artifacts" in observed["prompt"]
    assert "agent.codex-incident-responder" in observed["prompt"]
    assert "## Request JSON" in observed["prompt"]
    assert '"request_id": "compose-1"' in observed["prompt"]


def test_muse_prompt_layers_custom_contract_guidance_and_request(tmp_path, monkeypatch):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("CUSTOM CONTRACT\n", encoding="utf-8")
    guidance = tmp_path / "guidance.md"
    guidance.write_text("Environment fact: private development repository.\n", encoding="utf-8")
    monkeypatch.setenv("FORMALPROMPT_MUSE_PROMPT", str(prompt))
    monkeypatch.setenv("FORMALPROMPT_MUSE_GUIDANCE", str(guidance))
    request = AssistantRequest.model_validate(
        {
            "contract": "agent-canvas-assistant/v1",
            "request_id": "layered-1",
            "operation": "specification-review",
            "context": {"document": {}, "revision": 3},
        }
    )

    composed = _muse_prompt(request)

    contract_at = composed.index("CUSTOM CONTRACT")
    guidance_at = composed.index("## Environment guidance")
    request_at = composed.index("## Request JSON")
    assert contract_at < guidance_at < request_at
    assert "private development repository" in composed
    assert '"request_id": "layered-1"' in composed[request_at:]
    assert composed.endswith("\n")


def test_muse_prompt_rejects_oversized_guidance(tmp_path, monkeypatch):
    guidance = tmp_path / "guidance.md"
    guidance.write_bytes(b"x" * (MAX_PROMPT_BYTES + 1))
    monkeypatch.setenv("FORMALPROMPT_MUSE_GUIDANCE", str(guidance))
    request = AssistantRequest.model_validate(
        {
            "contract": "agent-canvas-assistant/v1",
            "request_id": "oversized-1",
            "operation": "initialization-compose",
            "context": {"document": {}, "revision": 1},
        }
    )

    with pytest.raises(MuseRunnerAdapterError, match="exceeds the 262144-byte limit"):
        _muse_prompt(request)


def test_muse_prompt_can_disable_seed_library(monkeypatch):
    monkeypatch.setenv("FORMALPROMPT_MUSE_LIBRARY", "none")
    request = AssistantRequest.model_validate(
        {
            "contract": "agent-canvas-assistant/v1",
            "request_id": "no-library-1",
            "operation": "initialization-compose",
            "context": {"document": {}, "revision": 1},
        }
    )

    composed = _muse_prompt(request)

    assert "## Available seed artifacts" not in composed
    assert "## Request JSON" in composed


def test_muse_prompt_rejects_artifact_path_outside_library(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    (tmp_path / "outside.md").write_text("not library content", encoding="utf-8")
    (library / "catalog.json").write_text(
        json.dumps(
            {
                "contract": "formalprompt-artifact-catalog/v1",
                "artifacts": [{"id": "escape", "path": "../outside.md"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FORMALPROMPT_MUSE_LIBRARY", str(library))
    request = AssistantRequest.model_validate(
        {
            "contract": "agent-canvas-assistant/v1",
            "request_id": "escape-1",
            "operation": "initialization-compose",
            "context": {"document": {}, "revision": 1},
        }
    )

    with pytest.raises(MuseRunnerAdapterError, match="escapes the library directory"):
        _muse_prompt(request)
