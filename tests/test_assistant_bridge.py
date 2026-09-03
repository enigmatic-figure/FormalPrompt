from __future__ import annotations

import json
import sys

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
