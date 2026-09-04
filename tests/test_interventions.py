from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

from formalprompt.cli import app
from formalprompt.compiler import compile_run
from formalprompt.interventions import (
    AUDIT_INDEX_CONTRACT,
    INTERVENTION_CONTRACT,
    INTERVENTION_EVENT,
    InterventionError,
    collect_audit_index,
    record_intervention,
)
from formalprompt.store import RunStore
from tests.workflow_helpers import workflow_document

runner = CliRunner()


def _git(repo, *arguments):
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()


def _repository(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "FormalPrompt Test")
    _git(repo, "config", "user.email", "formalprompt@example.invalid")
    (repo / "README.md").write_text("initialized\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "Initialize")
    return repo


def _compiled_run(tmp_path):
    store = RunStore.create(tmp_path / "runs", workflow_document(), run_id="workflow-run")
    store.approve("Local user", 0)
    compile_run(store, 0)
    return store


def test_intervention_is_an_exact_sparse_marker_in_existing_event_stream(tmp_path):
    repo = _repository(tmp_path)
    store = _compiled_run(tmp_path)

    marker = record_intervention(
        store.path,
        graph_node="implement",
        repository=repo,
    )

    assert marker["session_event"].startswith("formalprompt-intervention:")
    assert marker == {
        "contract": INTERVENTION_CONTRACT,
        "run_id": "workflow-run",
        "graph_node": "implement",
        "session_event": marker["session_event"],
        "git_head": _git(repo, "rev-parse", "HEAD"),
        "skill_version": "formalprompt-intervention/v1",
        "timestamp": marker["timestamp"],
    }
    assert not ({"problem", "cause", "adjustment", "recommendation"} & set(marker))
    event = json.loads((store.path / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event["type"] == INTERVENTION_EVENT
    assert event["target"] == "implement"
    assert event["summary"] == marker


def test_intervention_rejects_node_outside_approved_graph(tmp_path):
    repo = _repository(tmp_path)
    store = _compiled_run(tmp_path)

    with pytest.raises(InterventionError, match="Unknown workflow node"):
        record_intervention(store.path, graph_node="invented", repository=repo)


def test_collector_indexes_sources_without_copying_session_history(tmp_path):
    repo = _repository(tmp_path)
    store = _compiled_run(tmp_path)
    marker = record_intervention(
        store.path,
        graph_node="implement",
        repository=repo,
        session_event="intervention-anchor",
    )
    session_log = tmp_path / "session.jsonl"
    session_log.write_text(
        "before\nprivate surrounding detail\nintervention-anchor\nafter\n",
        encoding="utf-8",
    )
    (repo / "implementation.py").write_text("completed = True\n", encoding="utf-8")
    _git(repo, "add", "implementation.py")
    _git(repo, "commit", "-m", "Implement")
    head = _git(repo, "rev-parse", "HEAD")

    index = collect_audit_index(
        store.path,
        repository=repo,
        session_log=session_log,
        window_lines=1,
    )

    assert index["contract"] == AUDIT_INDEX_CONTRACT
    assert index["run_id"] == "workflow-run"
    assert len(index["interventions"]) == 1
    entry = index["interventions"][0]
    assert entry["marker"] == marker
    assert entry["workflow_node"] == {
        "id": "implement",
        "path": str((store.path / "artifacts" / "workflow.json").resolve()),
        "json_pointer": "/workflow/nodes/1",
        "resource_ids": ["agent.codex", "prompt.implement", "tool.terminal"],
    }
    assert entry["session_window"] == {
        "path": str(session_log.resolve()),
        "anchor": "intervention-anchor",
        "matches": [{"anchor_line": 3, "start_line": 2, "end_line": 4}],
    }
    assert entry["git"]["relationship"] == "ancestor"
    assert entry["git"]["collection_head"] == head
    assert entry["git"]["nearest_descendant"] == head
    assert entry["git"]["diff_range"] == f"{marker['git_head']}..{head}"
    written = (store.path / "intervention-audit-index.json").read_text(encoding="utf-8")
    assert "private surrounding detail" not in written
    assert "root_cause" not in written
    assert "recommendation" not in written


def test_collector_refuses_to_replace_index_without_force(tmp_path):
    repo = _repository(tmp_path)
    store = _compiled_run(tmp_path)
    collect_audit_index(store.path, repository=repo)

    with pytest.raises(InterventionError, match="Refusing to replace"):
        collect_audit_index(store.path, repository=repo)

    replaced = collect_audit_index(store.path, repository=repo, force=True)
    assert replaced["interventions"] == []


def test_cli_records_marker_and_builds_index(tmp_path):
    repo = _repository(tmp_path)
    store = _compiled_run(tmp_path)

    flagged = runner.invoke(
        app,
        [
            "intervene",
            str(store.path),
            "--node",
            "implement",
            "--project",
            str(repo),
            "--session-event",
            "cli-anchor",
            "--json",
        ],
    )
    assert flagged.exit_code == 0
    assert json.loads(flagged.stdout)["session_event"] == "cli-anchor"

    collected = runner.invoke(
        app,
        ["audit-index", str(store.path), "--project", str(repo), "--json"],
    )
    assert collected.exit_code == 0
    assert len(json.loads(collected.stdout)["interventions"]) == 1
