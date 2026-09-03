from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from fastapi.testclient import TestClient

from formalprompt.artifacts import verify_compiled_run
from formalprompt.compiler import compile_run
from formalprompt.models import CanvasDocument
from formalprompt.server import create_app
from formalprompt.store import RunStore
from formalprompt.validation import validate_document
from tests.workflow_helpers import workflow_document


def test_valid_typed_workflow_dag_has_no_semantic_issues():
    document = CanvasDocument.model_validate(workflow_document())

    assert validate_document(document) == []
    assert [node.kind for node in document.workflow.nodes] == [
        "input",
        "agent",
        "operation",
        "review",
        "gate",
        "operation",
    ]


def test_workflow_validation_rejects_cycles_broken_ports_and_resources():
    document = workflow_document()
    graph = document["workflow"]
    graph["edges"].append(
        {
            "id": "cycle",
            "source_node": "handoff",
            "source_port": "missing",
            "target_node": "implement",
            "target_port": "start",
            "data_type": "control",
        }
    )
    graph["nodes"][1]["prompt_resource"] = "missing.prompt"

    issues = validate_document(document)
    codes = {issue.code for issue in issues}

    assert "workflow-cycle" in codes
    assert "unknown-edge-source-port" in codes
    assert "unknown-node-resource" in codes
    assert "completion-node-has-output" in codes


def test_workflow_validation_rejects_unpinned_capability_and_unsafe_scope():
    document = workflow_document()
    resources = document["workflow"]["resources"]
    next(resource for resource in resources if resource["id"] == "tool.terminal")["version"] = None
    document["workflow"]["nodes"][1]["write_scope"].append("../outside/**")

    codes = {issue.code for issue in validate_document(document)}

    assert "unpinned-workflow-capability" in codes
    assert "unsafe-agent-write-scope" in codes


def test_workflow_validation_rejects_mistyped_artifact_and_incomplete_independence():
    document = workflow_document()
    document["workflow"]["resources"][0]["kind"] = "tool"
    document["workflow"]["nodes"][3]["independent_from"] = []

    codes = {issue.code for issue in validate_document(document)}

    assert "incompatible-workflow-artifact" in codes
    assert "review-independence-incomplete" in codes


def test_unresolved_workflow_state_blocks_approval_regardless_of_importance():
    document = workflow_document()
    document["workflow"]["nodes"][1]["importance"] = "low"
    document["workflow"]["nodes"][1]["review_status"] = "needs-input"

    codes = {issue.code for issue in validate_document(document)}

    assert "unresolved-workflow-node" in codes


def test_workflow_update_is_revision_safe_and_invalidates_approval(tmp_path):
    store = RunStore.create(tmp_path, workflow_document())
    store.approve("Local user", 0)
    client = TestClient(create_app(store, token="token"))
    workflow = store.read_document().workflow.model_dump(mode="json")
    workflow["nodes"][1]["position"] = {"x": 420, "y": 260}

    updated = client.put(
        "/api/workflow",
        headers={"Authorization": "Bearer token"},
        json={"workflow": workflow, "expected_revision": 0},
    )
    stale = client.put(
        "/api/workflow",
        headers={"Authorization": "Bearer token"},
        json={"workflow": workflow, "expected_revision": 0},
    )

    assert updated.status_code == 200
    assert updated.json()["state"]["revision"] == 1
    assert updated.json()["state"]["approval"] is None
    changed = next(
        node
        for node in updated.json()["document"]["workflow"]["nodes"]
        if node["id"] == "implement"
    )
    assert changed["position"] == {"x": 420.0, "y": 260.0}
    assert changed["provenance"] == "proposed"
    assert stale.status_code == 409


def test_explicit_node_declaration_save_records_user_confirmation(tmp_path):
    store = RunStore.create(tmp_path, workflow_document())
    client = TestClient(create_app(store, token="token"))
    workflow = store.read_document().workflow.model_dump(mode="json")
    workflow["nodes"][1]["title"] = "Confirmed implementation"

    response = client.put(
        "/api/workflow",
        headers={"Authorization": "Bearer token"},
        json={
            "workflow": workflow,
            "expected_revision": 0,
            "confirmed_node_ids": ["implement"],
        },
    )

    changed = next(
        node
        for node in response.json()["document"]["workflow"]["nodes"]
        if node["id"] == "implement"
    )
    assert changed["title"] == "Confirmed implementation"
    assert changed["provenance"] == "user-confirmed"
    assert changed["review_status"] == "accepted"


def test_compiler_emits_digest_bound_workflow_and_execution_contract(tmp_path):
    store = RunStore.create(tmp_path, workflow_document())
    store.approve("Local user", 0)

    result = compile_run(store, 0)
    verified, manifest = verify_compiled_run(store.path)

    assert verified == result
    assert result["workflow"] == "artifacts/workflow.json"
    assert result["execution_contract"] == "artifacts/EXECUTION_CONTRACT.md"
    assert "workflow.json" in manifest["files"]
    assert "EXECUTION_CONTRACT.md" in manifest["files"]
    contract = (store.path / "artifacts" / "EXECUTION_CONTRACT.md").read_text(encoding="utf-8")
    assert "Topological execution order" in contract
    assert "Review" in contract


def test_workflow_tampering_is_rejected_by_bundle_verifier(tmp_path):
    store = RunStore.create(tmp_path, workflow_document())
    store.approve("Local user", 0)
    compile_run(store, 0)
    workflow_path = store.path / "artifacts" / "workflow.json"
    workflow_path.write_text("{}", encoding="utf-8")

    from formalprompt.artifacts import ArtifactBundleError

    try:
        verify_compiled_run(store.path)
    except ArtifactBundleError as exc:
        assert "does not match manifest" in str(exc)
    else:
        raise AssertionError("Tampered workflow should not verify")


def test_workflow_derivation_rejects_coordinated_manifest_tampering(tmp_path):
    store = RunStore.create(tmp_path, workflow_document())
    store.approve("Local user", 0)
    compile_run(store, 0)
    contract_path = store.path / "artifacts" / "EXECUTION_CONTRACT.md"
    contract_path.write_text("# Replaced contract\n", encoding="utf-8")
    manifest_path = store.path / "artifacts" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    content = contract_path.read_bytes()
    manifest["files"]["EXECUTION_CONTRACT.md"] = {
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result_path = store.path / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["artifacts"] = manifest["files"]
    result_path.write_text(json.dumps(result), encoding="utf-8")

    from formalprompt.artifacts import ArtifactBundleError

    try:
        verify_compiled_run(store.path)
    except ArtifactBundleError as exc:
        assert "does not match the approved document" in str(exc)
    else:
        raise AssertionError("Re-derived workflow contract should reject coordinated tampering")


def test_workflow_result_cannot_omit_compiled_workflow_declaration(tmp_path):
    store = RunStore.create(tmp_path, workflow_document())
    store.approve("Local user", 0)
    compile_run(store, 0)
    result_path = store.path / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.pop("workflow")
    result.pop("execution_contract")
    result_path.write_text(json.dumps(result), encoding="utf-8")

    from formalprompt.artifacts import ArtifactBundleError

    try:
        verify_compiled_run(store.path)
    except ArtifactBundleError as exc:
        assert "does not match the approved document" in str(exc)
    else:
        raise AssertionError("Workflow result declarations are required")


def test_unreachable_workflow_node_blocks_approval():
    document = deepcopy(workflow_document())
    document["workflow"]["nodes"].append(
        {
            "id": "orphan",
            "kind": "join",
            "title": "Orphan",
            "position": {"x": 400, "y": 500},
            "provenance": "proposed",
            "review_status": "unreviewed",
        }
    )

    codes = {issue.code for issue in validate_document(document)}

    assert "workflow-node-unreachable" in codes
    assert "workflow-node-no-completion-path" in codes
