from __future__ import annotations

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from formalprompt.assistant import AssistantResponse
from formalprompt.server import create_app
from formalprompt.store import RunStore, ValidationFailed
from tests.test_session_api import minimal_document


class InitializationComposer:
    def invoke(self, request):
        document = deepcopy(request["context"]["document"])
        document["initialization"] = {
            "primary_artifact": "primary.prompt",
            "artifacts": [
                {
                    "id": "primary.prompt",
                    "path": "prompts/PRIMARY_AGENT.md",
                    "kind": "primary-prompt",
                    "title": "Primary execution prompt",
                    "content": "Execute the approved specification.",
                    "description": "Compact handoff for the context-preserved agent.",
                    "provenance": "proposed",
                    "review_status": "unreviewed",
                    "importance": "high",
                    "rationale": "Keeps initialization reasoning outside the primary context.",
                }
            ],
        }
        document["completion"]["require_independent_review"] = True
        return AssistantResponse.model_validate(
            {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request["request_id"],
                "summary": "The specification is ready for an initialization package.",
                "suggestions": [],
                "questions": [],
                "disposition": "ready",
                "next_document": document,
            }
        )


class ReadyCritic:
    def invoke(self, request):
        assert request["operation"] == "specification-review"
        assert request["context"]["role"] == "critic"
        return AssistantResponse.model_validate(
            {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request["request_id"],
                "summary": "The current revision is internally consistent and executable.",
                "suggestions": [],
                "questions": [],
                "disposition": "ready",
                "next_document": None,
            }
        )


class ChangesCritic:
    def invoke(self, request):
        return AssistantResponse.model_validate(
            {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request["request_id"],
                "summary": "The acceptance criterion is ambiguous.",
                "suggestions": [],
                "questions": ["What observable result proves completion?"],
                "disposition": "needs-clarification",
                "next_document": None,
            }
        )


class UnsafeComposer:
    def invoke(self, request):
        document = deepcopy(request["context"]["document"])
        document["initialization"] = {
            "primary_artifact": "escape",
            "artifacts": [
                {
                    "id": "escape",
                    "path": "../outside.md",
                    "kind": "other",
                    "title": "Unsafe output",
                    "content": "Do not stage this.",
                    "provenance": "proposed",
                    "review_status": "unreviewed",
                }
            ],
        }
        return AssistantResponse.model_validate(
            {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request["request_id"],
                "summary": "Unsafe proposal for rejection testing.",
                "suggestions": [],
                "questions": [],
                "disposition": "ready",
                "next_document": document,
            }
        )


class ClarificationComposer:
    def invoke(self, request):
        document = deepcopy(request["context"]["document"])
        document["tabs"][0]["sections"][0]["fields"].append(
            {
                "id": "project.delivery",
                "label": "Delivery format",
                "type": "textarea",
                "value": "",
                "required": True,
                "importance": "blocker",
                "provenance": "unresolved",
                "review_status": "needs-input",
            }
        )
        return AssistantResponse.model_validate(
            {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request["request_id"],
                "summary": "One consequential answer is still needed.",
                "suggestions": [],
                "questions": ["What should this project build?"],
                "disposition": "needs-clarification",
                "next_document": document,
            }
        )


def test_critic_pass_is_bound_to_the_reviewed_document_digest(tmp_path):
    document = minimal_document()
    document["completion"]["require_independent_review"] = True
    store = RunStore.create(tmp_path, document)

    reviewed = store.request_review("critic", "Check the current document", ReadyCritic())
    review_state = store.read_state()["independent_review"]
    assert reviewed["review_applied"] is True
    assert len(review_state["document_sha256"]) == 64

    changed = store.read_document().model_dump(mode="json")
    changed["tabs"][0]["sections"][0]["fields"][0]["value"] = "Changed after critic pass"
    (store.path / "document.json").write_text(json.dumps(changed), encoding="utf-8")

    codes = {issue.code for issue in store.validation_issues()}
    assert "independent-review-required" in codes
    with pytest.raises(ValidationFailed):
        store.approve("Local user", 0)


def test_composer_proposal_is_user_applied_edited_and_compiled(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(
        create_app(
            store,
            token="token",
            assistant=InitializationComposer(),
            reviewer=ReadyCritic(),
        )
    )
    headers = {"Authorization": "Bearer token"}

    composed = client.post(
        "/api/compose",
        headers=headers,
        json={"focus": "Create the smallest useful initialization package."},
    )
    request_id = composed.json()["request_id"]

    assert composed.status_code == 200
    assert composed.json()["response"]["disposition"] == "ready"
    assert store.read_state()["revision"] == 0
    assert store.read_document().initialization.artifacts == []

    applied = client.post(
        "/api/proposals/apply",
        headers=headers,
        json={"request_id": request_id, "expected_revision": 0},
    )
    edited = client.patch(
        "/api/artifacts/primary.prompt",
        headers=headers,
        json={"content": "Execute only the approved scope.", "expected_revision": 1},
    )
    blocked_approval = client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 2},
    )
    reviewed = client.post(
        "/api/review",
        headers=headers,
        json={"role": "critic", "focus": "Check the finished initialization package."},
    )
    approved = client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 2},
    )
    compiled = client.post("/api/compile", headers=headers, json={"expected_revision": 2})

    assert applied.status_code == 200
    assert edited.status_code == 200
    assert blocked_approval.status_code == 422
    assert reviewed.status_code == 200
    assert reviewed.json()["review_applied"] is True
    assert store.read_state()["independent_review"]["status"] == "passed"
    assert approved.status_code == 200
    assert compiled.status_code == 200
    assert compiled.json()["handoff"] == ("artifacts/initialization/prompts/PRIMARY_AGENT.md")
    staged = store.path / "artifacts" / "initialization" / "prompts" / "PRIMARY_AGENT.md"
    assert staged.read_text(encoding="utf-8") == "Execute only the approved scope.\n"
    assert "initialization/prompts/PRIMARY_AGENT.md" in compiled.json()["artifacts"]


def test_unsafe_initialization_artifact_path_blocks_approval(tmp_path):
    document = minimal_document()
    document["initialization"] = {
        "primary_artifact": "escape",
        "artifacts": [
            {
                "id": "escape",
                "path": "../outside.md",
                "kind": "other",
                "title": "Unsafe output",
                "content": "Must remain inside the run.",
                "provenance": "proposed",
                "review_status": "unreviewed",
            }
        ],
    }
    store = RunStore.create(tmp_path, document)
    client = TestClient(create_app(store, token="token"))

    response = client.post(
        "/api/approve",
        headers={"Authorization": "Bearer token"},
        json={"approved_by": "Local user", "expected_revision": 0},
    )

    assert response.status_code == 422
    codes = {issue["code"] for issue in response.json()["detail"]["issues"]}
    assert "unsafe-artifact-path" in codes


def test_unsafe_composer_proposal_is_not_applied(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(create_app(store, token="token", assistant=UnsafeComposer()))
    headers = {"Authorization": "Bearer token"}
    composed = client.post(
        "/api/compose", headers=headers, json={"focus": "Return an unsafe proposal."}
    )

    response = client.post(
        "/api/proposals/apply",
        headers=headers,
        json={"request_id": composed.json()["request_id"], "expected_revision": 0},
    )

    assert response.status_code == 422
    assert store.read_state()["revision"] == 0
    assert store.read_document().initialization.artifacts == []


def test_intentional_clarification_canvas_can_be_applied(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(create_app(store, token="token", assistant=ClarificationComposer()))
    headers = {"Authorization": "Bearer token"}
    composed = client.post(
        "/api/compose", headers=headers, json={"focus": "Ask the remaining blocker."}
    )

    response = client.post(
        "/api/proposals/apply",
        headers=headers,
        json={"request_id": composed.json()["request_id"], "expected_revision": 0},
    )

    assert response.status_code == 200
    assert response.json()["state"]["revision"] == 1
    assert (
        response.json()["document"]["tabs"][0]["sections"][0]["fields"][1]["provenance"]
        == "unresolved"
    )


class ConfirmedFactMutationComposer:
    def invoke(self, request):
        document = deepcopy(request["context"]["document"])
        document["tabs"][0]["sections"][0]["fields"][0]["value"] = "Replace the thing"
        return AssistantResponse.model_validate(
            {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request["request_id"],
                "summary": "Attempted to replace a confirmed fact.",
                "suggestions": [],
                "questions": [],
                "disposition": "ready",
                "next_document": document,
            }
        )


def test_assistant_proposal_cannot_replace_confirmed_fact(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(create_app(store, token="token", assistant=ConfirmedFactMutationComposer()))
    headers = {"Authorization": "Bearer token"}
    composed = client.post("/api/compose", headers=headers, json={"focus": "Mutate intent."})

    response = client.post(
        "/api/proposals/apply",
        headers=headers,
        json={"request_id": composed.json()["request_id"], "expected_revision": 0},
    )

    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert any(
        issue["code"] == "confirmed-fact-modified"
        and "confirmed field project.goal" in issue["message"]
        for issue in issues
    )
    assert store.read_document().fields()[0].value == "Build the thing"


def test_compiled_run_rejects_further_edits(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(create_app(store, token="token"))
    headers = {"Authorization": "Bearer token"}
    client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 0},
    )
    client.post("/api/compile", headers=headers, json={"expected_revision": 0})

    response = client.patch(
        "/api/fields/project.goal",
        headers=headers,
        json={"value": "Mutate a terminal run", "expected_revision": 0},
    )

    assert response.status_code == 409
    assert store.read_document().fields()[0].value == "Build the thing"


def test_negative_critic_review_invalidates_an_existing_approval(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(create_app(store, token="token", reviewer=ChangesCritic()))
    headers = {"Authorization": "Bearer token"}
    approved = client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 0},
    )

    reviewed = client.post(
        "/api/review",
        headers=headers,
        json={"role": "critic", "focus": "Challenge the approved revision."},
    )
    compiled = client.post("/api/compile", headers=headers, json={"expected_revision": 0})

    assert approved.status_code == 200
    assert reviewed.status_code == 200
    assert store.read_state()["approval"] is None
    assert store.read_state()["status"] == "user-editing"
    assert compiled.status_code == 409
