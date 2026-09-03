from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from formalprompt.artifacts import verify_compiled_run
from formalprompt.compiler import ApprovalRequired, compile_run, recover_interrupted_compilation
from formalprompt.server import create_app
from formalprompt.store import RunStore
from tests.test_session_api import minimal_document


def _client(store: RunStore) -> tuple[TestClient, dict[str, str]]:
    return TestClient(create_app(store, token="token")), {"Authorization": "Bearer token"}


def test_invalid_document_cannot_be_approved(tmp_path):
    document = minimal_document()
    field = document["tabs"][0]["sections"][0]["fields"][0]
    field["value"] = ""
    field["provenance"] = "unresolved"
    field["review_status"] = "needs-input"
    store = RunStore.create(tmp_path, document)
    client, headers = _client(store)

    response = client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 0},
    )

    assert response.status_code == 422
    codes = {issue["code"] for issue in response.json()["detail"]["issues"]}
    assert codes == {"required-value-missing", "unresolved-blocker"}
    assert store.read_state()["approval"] is None


def test_approved_revision_compiles_to_a_hashed_handoff_bundle(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client, headers = _client(store)

    approval = client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 0},
    )
    compiled = client.post(
        "/api/compile",
        headers=headers,
        json={"expected_revision": 0},
    )

    assert approval.status_code == 200
    assert approval.json()["state"]["status"] == "approved"
    assert len(approval.json()["state"]["approval"]["document_sha256"]) == 64
    assert compiled.status_code == 200
    result = compiled.json()
    assert result["contract"] == "agent-canvas-result/v1"
    assert result["status"] == "compiled"
    assert result["revision"] == 0
    assert result["unresolved_count"] == 0
    assert result["handoff"] == "artifacts/EXECUTION_BRIEF.md"

    artifacts = store.path / "artifacts"
    expected = {
        "specification.json",
        "SPECIFICATION.md",
        "EXECUTION_BRIEF.md",
        "approval.json",
        "manifest.json",
    }
    assert {path.name for path in artifacts.iterdir()} == expected
    manifest = json.loads((artifacts / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == expected - {"manifest.json"}
    assert all(len(metadata["sha256"]) == 64 for metadata in manifest["files"].values())
    assert "Build the thing" in (artifacts / "EXECUTION_BRIEF.md").read_text(encoding="utf-8")
    persisted_result = json.loads((store.path / "result.json").read_text(encoding="utf-8"))
    assert persisted_result == result


def test_result_is_published_before_compiled_state(tmp_path, monkeypatch):
    store = RunStore.create(tmp_path, minimal_document())
    client, headers = _client(store)
    client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 0},
    )
    original_mark_compiled = store.mark_compiled
    result_was_durable = []

    def observe_publication_order(expected_revision):
        result_was_durable.append((store.path / "result.json").is_file())
        original_mark_compiled(expected_revision)

    monkeypatch.setattr(store, "mark_compiled", observe_publication_order)

    response = client.post(
        "/api/compile",
        headers=headers,
        json={"expected_revision": 0},
    )

    assert response.status_code == 200
    assert result_was_durable == [True]


def test_compiled_run_cannot_be_compiled_again(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client, headers = _client(store)
    client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 0},
    )
    first = client.post(
        "/api/compile",
        headers=headers,
        json={"expected_revision": 0},
    )

    second = client.post(
        "/api/compile",
        headers=headers,
        json={"expected_revision": 0},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert "already compiled" in second.json()["detail"].lower()


def test_compiled_run_cannot_be_approved_again(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client, headers = _client(store)
    client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 0},
    )
    client.post(
        "/api/compile",
        headers=headers,
        json={"expected_revision": 0},
    )

    response = client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Second approver", "expected_revision": 0},
    )

    assert response.status_code == 409
    assert store.read_state()["status"] == "compiled"


def test_edit_after_approval_invalidates_approval(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    client, headers = _client(store)
    client.post(
        "/api/approve",
        headers=headers,
        json={"approved_by": "Local user", "expected_revision": 0},
    )

    edited = client.patch(
        "/api/fields/project.goal",
        headers=headers,
        json={"value": "A changed goal", "expected_revision": 0},
    )
    compile_response = client.post("/api/compile", headers=headers, json={"expected_revision": 1})

    assert edited.status_code == 200
    assert edited.json()["state"]["approval"] is None
    assert compile_response.status_code == 409


def test_approval_is_bound_to_exact_document_contents(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    store.approve("Local user", 0)
    changed = store.read_document().model_dump(mode="json")
    changed["tabs"][0]["sections"][0]["fields"][0]["value"] = "Silently changed"
    (store.path / "document.json").write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(ApprovalRequired, match="contents have changed"):
        compile_run(store, 0)

    assert store.read_state()["status"] == "approved"


def test_recovery_restores_incomplete_compilation_for_retry(tmp_path):
    store = RunStore.create(tmp_path, minimal_document())
    store.approve("Local user", 0)
    store.begin_compilation(0)
    artifacts = store.path / "artifacts"
    artifacts.mkdir()
    (artifacts / "partial.tmp").write_text("partial", encoding="utf-8")

    action = recover_interrupted_compilation(store)

    assert action == "restored-approved"
    assert store.read_state()["status"] == "approved"
    assert not artifacts.exists()
    assert compile_run(store, 0)["status"] == "compiled"


def test_recovery_finalizes_complete_bundle_published_before_state(tmp_path, monkeypatch):
    store = RunStore.create(tmp_path, minimal_document())
    store.approve("Local user", 0)
    original_mark_compiled = store.mark_compiled
    monkeypatch.setattr(
        store, "mark_compiled", lambda revision: (_ for _ in ()).throw(KeyboardInterrupt())
    )

    with pytest.raises(KeyboardInterrupt):
        compile_run(store, 0)

    assert store.read_state()["status"] == "compiling"
    monkeypatch.setattr(store, "mark_compiled", original_mark_compiled)
    assert recover_interrupted_compilation(store) == "finalized-compiled"
    assert store.read_state()["status"] == "compiled"
    result, manifest = verify_compiled_run(store.path)
    assert result["document_sha256"] == manifest["document_sha256"]
