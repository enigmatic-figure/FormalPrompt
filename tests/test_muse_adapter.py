from __future__ import annotations

import json

from formalprompt.adapters.muse_runner import invoke_muse
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
