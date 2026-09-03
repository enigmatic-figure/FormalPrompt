from __future__ import annotations

import json
import subprocess

import pytest

from formalprompt.artifacts import ArtifactBundleError, materialize_initialization
from formalprompt.compiler import compile_run
from formalprompt.git_lifecycle import (
    DEFAULT_BASELINE_TAG,
    GitLifecycleError,
    create_checkpoint,
    create_retrospective,
    record_learning,
)
from formalprompt.store import RunStore
from tests.test_session_api import minimal_document


def _compiled_initialization_run(tmp_path):
    document = minimal_document()
    document["initialization"] = {
        "primary_artifact": "agent.rules",
        "artifacts": [
            {
                "id": "agent.rules",
                "path": "AGENTS.md",
                "kind": "agent-definition",
                "title": "Project agent rules",
                "content": "# Project rules\n\nPreserve the approved scope.\n",
                "provenance": "user-confirmed",
                "review_status": "accepted",
                "importance": "high",
            }
        ],
    }
    store = RunStore.create(tmp_path / "runs", document)
    store.approve("Local user", 0)
    compile_run(store, 0)
    return store


def _git(repo, *arguments):
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()


def _initialize_repository(repo):
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "FormalPrompt Test")
    _git(repo, "config", "user.email", "formalprompt@example.invalid")
    (repo / "AGENTS.md").write_text("# Initial rules\n", encoding="utf-8")
    _git(repo, "add", "AGENTS.md")
    _git(repo, "commit", "-m", "Initialize project")


def test_materialize_verifies_bundle_and_writes_only_initialization_files(tmp_path):
    store = _compiled_initialization_run(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    written = materialize_initialization(store.path, project)

    assert written == [project / "AGENTS.md"]
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == (
        "# Project rules\n\nPreserve the approved scope.\n"
    )
    assert not (project / "EXECUTION_BRIEF.md").exists()


def test_materialize_rejects_a_tampered_compiled_artifact(tmp_path):
    store = _compiled_initialization_run(tmp_path)
    artifact = store.path / "artifacts" / "initialization" / "AGENTS.md"
    artifact.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ArtifactBundleError, match="does not match manifest"):
        materialize_initialization(store.path, tmp_path / "project")


def test_checkpoint_and_retrospective_preserve_and_compare_true_initialization(tmp_path):
    repo = tmp_path / "project"
    _initialize_repository(repo)

    checkpoint = create_checkpoint(repo)

    assert checkpoint["tag"] == DEFAULT_BASELINE_TAG
    assert checkpoint["commit"] == _git(repo, "rev-parse", "HEAD")
    annotation = _git(repo, "tag", "--list", DEFAULT_BASELINE_TAG, "--format=%(contents)")
    assert json.loads(annotation)["contract"] == "formalprompt-initialization-checkpoint/v1"

    (repo / "AGENTS.md").write_text("# Improved rules\n", encoding="utf-8")
    record_learning(
        repo,
        artifact="AGENTS.md",
        problem="The execution agent changed files outside its owned subsystem.",
        adjustment="Added explicit file ownership boundaries.",
        recommendation="Teach initialization templates to assign artifact ownership.",
        evidence="The corrected run completed without overlapping edits.",
    )
    _git(repo, "add", "AGENTS.md", ".formalprompt-learning.jsonl")
    _git(repo, "commit", "-m", "Correct execution governance")
    report = repo / "INITIALIZATION_RETROSPECTIVE.md"
    patch = repo / "INITIALIZATION_RETROSPECTIVE.patch"

    result = create_retrospective(repo, output=report, patch_output=patch)

    assert result["changed_files"] == 2
    assert result["initialization_sensitive_files"] == 2
    assert result["learning_records"] == 1
    assert "Teach initialization templates" in report.read_text(encoding="utf-8")
    assert "AGENTS.md" in patch.read_text(encoding="utf-8")


def test_checkpoint_requires_a_clean_committed_tree(tmp_path):
    repo = tmp_path / "project"
    _initialize_repository(repo)
    (repo / "uncommitted.txt").write_text("not ready\n", encoding="utf-8")

    with pytest.raises(GitLifecycleError, match="clean committed"):
        create_checkpoint(repo)
