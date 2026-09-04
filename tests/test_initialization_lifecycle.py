from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from formalprompt.artifacts import ArtifactBundleError, materialize_initialization
from formalprompt.compiler import compile_run
from formalprompt.git_lifecycle import (
    DEFAULT_BASELINE_TAG,
    GitLifecycleError,
    _format_change,
    _is_initialization_sensitive_change,
    _parse_name_status,
    create_checkpoint,
    create_retrospective,
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


def test_materialize_rolls_back_all_targets_if_commit_fails(tmp_path, monkeypatch):
    document = minimal_document()
    document["initialization"] = {
        "primary_artifact": "first",
        "artifacts": [
            {
                "id": "first",
                "path": "FIRST.md",
                "kind": "project-plan",
                "title": "First",
                "content": "new first",
                "provenance": "user-confirmed",
                "review_status": "accepted",
                "importance": "high",
            },
            {
                "id": "second",
                "path": "SECOND.md",
                "kind": "project-plan",
                "title": "Second",
                "content": "new second",
                "provenance": "user-confirmed",
                "review_status": "accepted",
                "importance": "high",
            },
        ],
    }
    store = RunStore.create(tmp_path / "rollback-runs", document)
    store.approve("Local user", 0)
    compile_run(store, 0)
    project = tmp_path / "project"
    project.mkdir()
    (project / "FIRST.md").write_text("old first", encoding="utf-8")
    (project / "SECOND.md").write_text("old second", encoding="utf-8")
    original_replace = Path.replace

    def fail_second_install(source, target):
        if source.name.endswith(".new") and Path(target).name == "SECOND.md":
            raise OSError("simulated failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_second_install)

    with pytest.raises(ArtifactBundleError, match="could not be committed"):
        materialize_initialization(store.path, project, force=True)

    assert (project / "FIRST.md").read_text(encoding="utf-8") == "old first"
    assert (project / "SECOND.md").read_text(encoding="utf-8") == "old second"


def test_checkpoint_and_retrospective_preserve_and_compare_true_initialization(tmp_path):
    repo = tmp_path / "project"
    _initialize_repository(repo)

    checkpoint = create_checkpoint(repo)

    assert checkpoint["tag"] == DEFAULT_BASELINE_TAG
    assert checkpoint["commit"] == _git(repo, "rev-parse", "HEAD")
    annotation = _git(repo, "tag", "--list", DEFAULT_BASELINE_TAG, "--format=%(contents)")
    assert json.loads(annotation)["contract"] == "formalprompt-initialization-checkpoint/v1"

    (repo / "AGENTS.md").write_text("# Improved rules\n", encoding="utf-8")
    _git(repo, "add", "AGENTS.md")
    _git(repo, "commit", "-m", "Correct execution governance")
    report = repo / "INITIALIZATION_RETROSPECTIVE.md"
    patch = repo / "INITIALIZATION_RETROSPECTIVE.patch"

    result = create_retrospective(repo, output=report, patch_output=patch)

    assert result["changed_files"] == 1
    assert result["initialization_sensitive_files"] == 1
    report_content = report.read_text(encoding="utf-8")
    assert "mechanically derived Git comparison" in report_content
    assert "recommend reusable-system changes" in report_content
    assert "AGENTS.md" in patch.read_text(encoding="utf-8")


def test_checkpoint_requires_a_clean_committed_tree(tmp_path):
    repo = tmp_path / "project"
    _initialize_repository(repo)
    (repo / "uncommitted.txt").write_text("not ready\n", encoding="utf-8")

    with pytest.raises(GitLifecycleError, match="clean committed"):
        create_checkpoint(repo)


def test_checkpoint_push_without_origin_does_not_leave_a_local_tag(tmp_path):
    repo = tmp_path / "project"
    _initialize_repository(repo)

    with pytest.raises(GitLifecycleError, match="without an origin"):
        create_checkpoint(repo, push=True)

    assert _git(repo, "tag", "--list", DEFAULT_BASELINE_TAG) == ""


def test_nul_name_status_parser_preserves_unusual_paths_and_rename_sources():
    raw = (
        "M\0docs/tab\tname.md\0"
        "A\0docs/line\nname.md\0"
        "A\0docs/café.md\0"
        "R100\0docs/renamed-from.md\0renamed.bin\0"
    )

    changes = _parse_name_status(raw)

    assert [change["path"] for change in changes[:3]] == [
        "docs/tab\tname.md",
        "docs/line\nname.md",
        "docs/café.md",
    ]
    assert changes[3] == {
        "status": "R100",
        "old_path": "docs/renamed-from.md",
        "path": "renamed.bin",
    }
    assert all(_is_initialization_sensitive_change(change) for change in changes)


def test_retrospective_escapes_control_characters_and_backticks_in_paths():
    rendered = _format_change(
        {"status": "R100", "old_path": "docs/line\n`old`.md", "path": "new\tname.md"}
    )

    assert rendered.count("\n") == 0
    assert "\\n\\u0060old\\u0060.md" in rendered
    assert "new\\tname.md" in rendered


def test_retrospective_handles_non_ascii_paths_and_sensitive_rename_sources(tmp_path):
    repo = tmp_path / "project"
    _initialize_repository(repo)
    docs = repo / "docs"
    docs.mkdir()
    renamed_from = docs / "rename-from.md"
    renamed_from.write_text("kept\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "Add rename source")
    create_checkpoint(repo)

    renamed_from.rename(repo / "renamed.bin")
    (docs / "café.md").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "Exercise unusual paths")

    result = create_retrospective(
        repo,
        output=repo / "RETROSPECTIVE.md",
        patch_output=repo / "RETROSPECTIVE.patch",
    )

    assert result["changed_files"] == 2
    assert result["initialization_sensitive_files"] == 2
