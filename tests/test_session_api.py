from __future__ import annotations

from fastapi.testclient import TestClient

from formalprompt.server import create_app
from formalprompt.store import RunStore


def minimal_document() -> dict:
    return {
        "protocol": "agent-canvas/v1",
        "kind": "formalprompt/specification",
        "metadata": {
            "title": "Test project",
            "description": "A minimal specification",
            "created_by": "test-agent",
        },
        "tabs": [
            {
                "id": "intent",
                "label": "Intent",
                "sections": [
                    {
                        "id": "goal",
                        "title": "Goal",
                        "fields": [
                            {
                                "id": "project.goal",
                                "label": "Project goal",
                                "type": "textarea",
                                "value": "Build the thing",
                                "required": True,
                                "importance": "blocker",
                                "provenance": "explicit",
                                "review_status": "accepted",
                            }
                        ],
                    }
                ],
            }
        ],
        "completion": {"require_user_approval": True},
    }


def test_created_run_is_durable_and_requires_its_bearer_token(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())

    assert (store.path / "document.json").is_file()
    assert (store.path / "state.json").is_file()
    assert (store.path / "events.jsonl").is_file()

    client = TestClient(create_app(store, token="secret-token"))

    unauthenticated = client.get("/api/session")
    authenticated = client.get("/api/session", headers={"Authorization": "Bearer secret-token"})

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    payload = authenticated.json()
    assert payload["run_id"] == store.run_id
    assert payload["state"]["status"] == "draft"
    assert payload["state"]["revision"] == 0
    assert payload["document"]["metadata"]["title"] == "Test project"
