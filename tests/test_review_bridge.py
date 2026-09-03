from __future__ import annotations

import json
import sys

from fastapi.testclient import TestClient

from formalprompt.assistant import CommandAssistant
from formalprompt.server import create_app
from formalprompt.store import RunStore
from tests.test_session_api import minimal_document


def test_specification_review_is_scoped_to_run_and_persisted(tmp_path):
    adapter_script = tmp_path / "reviewer.py"
    adapter_script.write_text(
        """import json, sys
request = json.load(sys.stdin)
assert request['operation'] == 'specification-review'
json.dump({
  'contract': 'agent-canvas-assistant/v1',
  'request_id': request['request_id'],
  'summary': 'One ambiguity remains.',
  'suggestions': [],
  'questions': ['What is the delivery deadline?']
}, sys.stdout)
""",
        encoding="utf-8",
    )
    backend = CommandAssistant([sys.executable, str(adapter_script)])
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(create_app(store, token="token", assistant=backend))

    response = client.post(
        "/api/review",
        headers={"Authorization": "Bearer token"},
        json={"role": "critic", "focus": "Find hidden execution ambiguity"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["response"]["questions"] == ["What is the delivery deadline?"]
    request = json.loads(
        (store.path / "requests" / f"{payload['request_id']}.json").read_text(encoding="utf-8")
    )
    assert request["context"]["role"] == "critic"
    assert request["context"]["document"]["metadata"]["title"] == "Test project"
    saved_response = store.path / "responses" / f"{payload['request_id']}.json"
    assert saved_response.is_file()


def test_specification_review_queues_when_no_backend_is_configured(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(create_app(store, token="token"))

    response = client.post(
        "/api/review",
        headers={"Authorization": "Bearer token"},
        json={"role": "facilitator", "focus": "Check completeness"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
