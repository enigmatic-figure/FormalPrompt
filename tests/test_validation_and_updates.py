from __future__ import annotations

import math
from copy import deepcopy

from fastapi.testclient import TestClient

from formalprompt.server import create_app
from formalprompt.store import RunStore
from formalprompt.validation import validate_document
from tests.test_session_api import minimal_document


def test_semantic_validation_reports_duplicate_ids_and_missing_blocker():
    document = minimal_document()
    duplicate = deepcopy(document["tabs"][0]["sections"][0]["fields"][0])
    duplicate["value"] = ""
    duplicate["provenance"] = "unresolved"
    duplicate["review_status"] = "needs-input"
    document["tabs"][0]["sections"][0]["fields"].append(duplicate)

    issues = validate_document(document)

    assert {issue.code for issue in issues} == {
        "duplicate-field-id",
        "required-value-missing",
        "unresolved-blocker",
    }
    assert all(issue.field_id == "project.goal" for issue in issues)


def test_user_update_advances_revision_and_rejects_stale_writes(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client = TestClient(create_app(store, token="token"))
    headers = {"Authorization": "Bearer token"}

    updated = client.patch(
        "/api/fields/project.goal",
        headers=headers,
        json={"value": "Build a validated canvas", "expected_revision": 0},
    )
    stale = client.patch(
        "/api/fields/project.goal",
        headers=headers,
        json={"value": "Overwrite it", "expected_revision": 0},
    )

    assert updated.status_code == 200
    assert updated.json()["state"]["revision"] == 1
    field = updated.json()["document"]["tabs"][0]["sections"][0]["fields"][0]
    assert field["value"] == "Build a validated canvas"
    assert field["provenance"] == "user-confirmed"
    assert field["review_status"] == "accepted"
    assert stale.status_code == 409
    assert store.read_document().fields()[0].value == "Build a validated canvas"

    events = (store.path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 2
    assert '"type":"field.updated"' in events[-1]


def test_malformed_field_rules_become_issues_instead_of_crashing():
    document = minimal_document()
    field = document["tabs"][0]["sections"][0]["fields"][0]
    field["type"] = "select"
    field["value"] = {"not": "a scalar"}
    field["options"] = [
        {"value": "one", "label": "One"},
        {"value": "one", "label": "Duplicate"},
    ]
    field["validation"] = {"pattern": "["}

    issues = validate_document(document)

    assert {issue.code for issue in issues} >= {
        "duplicate-option",
        "invalid-option",
        "invalid-pattern",
        "invalid-type",
    }


def test_invalid_candidate_value_is_not_persisted(tmp_path):
    document = minimal_document()
    field = document["tabs"][0]["sections"][0]["fields"][0]
    field["type"] = "select"
    field["value"] = "safe"
    field["options"] = [{"value": "safe", "label": "Safe"}]
    store = RunStore.create(tmp_path, document)
    client = TestClient(create_app(store, token="token"))

    response = client.patch(
        "/api/fields/project.goal",
        headers={"Authorization": "Bearer token"},
        json={"value": "not-an-option", "expected_revision": 0},
    )

    assert response.status_code == 422
    assert store.read_state()["revision"] == 0
    assert store.read_document().fields()[0].value == "safe"


def test_non_finite_number_is_rejected_before_json_handoff():
    document = minimal_document()
    field = document["tabs"][0]["sections"][0]["fields"][0]
    field["type"] = "number"
    field["value"] = math.inf

    issues = validate_document(document)

    assert {issue.code for issue in issues} == {"non-finite-number"}


def test_nested_quantifier_pattern_is_rejected_without_evaluating_user_value():
    document = minimal_document()
    field = document["tabs"][0]["sections"][0]["fields"][0]
    field["value"] = "a" * 100_000 + "!"
    field["validation"] = {"pattern": "(a+)+$"}

    issues = validate_document(document)

    assert {issue.code for issue in issues} == {"unsafe-pattern"}
