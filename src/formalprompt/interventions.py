from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from formalprompt.artifacts import ArtifactBundleError, verify_compiled_run
from formalprompt.store import RunStore

INTERVENTION_CONTRACT = "formalprompt-intervention-flag/v1"
AUDIT_INDEX_CONTRACT = "formalprompt-intervention-audit-index/v1"
INTERVENTION_EVENT = "intervention.flagged"
INTERVENTION_SKILL_VERSION = "formalprompt-intervention/v1"
DEFAULT_SESSION_WINDOW_LINES = 12
MARKER_FIELDS = {
    "contract",
    "run_id",
    "graph_node",
    "session_event",
    "git_head",
    "skill_version",
    "timestamp",
}


class InterventionError(RuntimeError):
    pass


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InterventionMarker(StrictContract):
    contract: Literal["formalprompt-intervention-flag/v1"]
    run_id: str = Field(min_length=1)
    graph_node: str = Field(min_length=1)
    session_event: str = Field(min_length=1)
    git_head: str = Field(min_length=1)
    skill_version: str = Field(min_length=1)
    timestamp: datetime


class FilePointer(StrictContract):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)


class EventPointer(StrictContract):
    path: str = Field(min_length=1)
    line: int = Field(ge=1)


class WorkflowNodePointer(StrictContract):
    id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    json_pointer: str = Field(min_length=1)
    resource_ids: list[str]


class SessionLineRange(StrictContract):
    anchor_line: int = Field(ge=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class SessionWindow(StrictContract):
    path: str = Field(min_length=1)
    anchor: str = Field(min_length=1)
    matches: list[SessionLineRange]


class GitBookmark(StrictContract):
    repository: str = Field(min_length=1)
    marker_head: str = Field(min_length=1)
    collection_head: str = Field(min_length=1)
    relationship: Literal["same", "ancestor", "diverged"]
    nearest_descendant: str | None
    diff_range: str | None


class InterventionEntry(StrictContract):
    marker: InterventionMarker
    event: EventPointer
    workflow_node: WorkflowNodePointer
    session_window: SessionWindow | None
    git: GitBookmark


class RepositoryPointer(StrictContract):
    path: str = Field(min_length=1)
    collection_head: str = Field(min_length=1)


class ArtifactPointer(StrictContract):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AuditSources(StrictContract):
    result: FilePointer
    workflow: FilePointer
    execution_contract: FilePointer
    manifest: FilePointer
    approved_document: FilePointer
    event_stream: FilePointer
    session_log: FilePointer | None
    repository: RepositoryPointer
    initialization_artifacts: list[ArtifactPointer]


class InterventionAuditIndex(StrictContract):
    contract: Literal["formalprompt-intervention-audit-index/v1"]
    run_id: str = Field(min_length=1)
    generated_at: datetime
    sources: AuditSources
    interventions: list[InterventionEntry]


def record_intervention(
    run_directory: Path,
    *,
    graph_node: str,
    repository: Path,
    session_event: str | None = None,
    skill_version: str = INTERVENTION_SKILL_VERSION,
) -> dict[str, str]:
    """Append a sparse correlation marker to a verified run's existing event stream."""
    result, _ = _verified_run(run_directory)
    workflow = _read_workflow(run_directory)
    nodes = _workflow_nodes(workflow)
    if graph_node not in nodes:
        raise InterventionError(f"Unknown workflow node: {graph_node}")
    marker = InterventionMarker(
        contract=INTERVENTION_CONTRACT,
        run_id=result["run_id"],
        graph_node=graph_node,
        session_event=session_event or f"formalprompt-intervention:{uuid4().hex}",
        git_head=_git_head(repository),
        skill_version=skill_version,
        timestamp=_now(),
    ).model_dump(mode="json")
    RunStore(run_directory.resolve()).append_event(
        INTERVENTION_EVENT,
        "agent",
        graph_node,
        marker,
    )
    return marker


def collect_audit_index(
    run_directory: Path,
    *,
    repository: Path,
    session_log: Path | None = None,
    output: Path | None = None,
    window_lines: int = DEFAULT_SESSION_WINDOW_LINES,
    force: bool = False,
) -> dict[str, Any]:
    """Build a deterministic bookmark index without copying session or Git history."""
    if window_lines < 0:
        raise InterventionError("Session window line count cannot be negative")
    result, manifest = _verified_run(run_directory)
    run_root = run_directory.resolve()
    workflow_path = run_root / "artifacts" / "workflow.json"
    workflow = _read_workflow(run_root)
    nodes = _workflow_nodes(workflow)
    events_path = run_root / "events.jsonl"
    markers = _read_markers(events_path, expected_run_id=result["run_id"])
    repo_root = _repository_root(repository)
    collection_head = _git(repo_root, "rev-parse", "HEAD")
    session_source = _session_source(session_log)

    entries = []
    for event_line, marker in markers:
        node_id = marker["graph_node"]
        if node_id not in nodes:
            raise InterventionError(
                f"Intervention event on line {event_line} references unknown node: {node_id}"
            )
        entries.append(
            {
                "marker": marker,
                "event": {"path": str(events_path), "line": event_line},
                "workflow_node": {
                    "id": node_id,
                    "path": str(workflow_path),
                    "json_pointer": _node_pointer(workflow, node_id),
                    "resource_ids": _node_resource_ids(nodes[node_id]),
                },
                "session_window": _session_window(
                    session_source,
                    marker["session_event"],
                    window_lines,
                ),
                "git": _git_bookmark(repo_root, marker["git_head"], collection_head),
            }
        )

    try:
        index = InterventionAuditIndex.model_validate(
            {
                "contract": AUDIT_INDEX_CONTRACT,
                "run_id": result["run_id"],
                "generated_at": _now(),
                "sources": {
                    "result": _file_pointer(run_root / "result.json"),
                    "workflow": _file_pointer(workflow_path),
                    "execution_contract": _file_pointer(
                        run_root / "artifacts" / "EXECUTION_CONTRACT.md"
                    ),
                    "manifest": _file_pointer(run_root / "artifacts" / "manifest.json"),
                    "approved_document": _file_pointer(run_root / "document.json"),
                    "event_stream": _file_pointer(events_path),
                    "session_log": session_source["pointer"] if session_source else None,
                    "repository": {
                        "path": str(repo_root),
                        "collection_head": collection_head,
                    },
                    "initialization_artifacts": [
                        {"path": relative, "sha256": details["sha256"]}
                        for relative, details in sorted(manifest["files"].items())
                        if relative.startswith("initialization/")
                    ],
                },
                "interventions": entries,
            }
        ).model_dump(mode="json")
    except ValidationError as exc:
        raise InterventionError("Generated intervention audit index is invalid") from exc
    destination = output.resolve() if output else run_root / "intervention-audit-index.json"
    if destination.exists() and not force:
        raise InterventionError(f"Refusing to replace existing audit index: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return index


def _verified_run(run_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        result, manifest = verify_compiled_run(run_directory)
    except (ArtifactBundleError, OSError, ValueError) as exc:
        raise InterventionError(f"Run is not a verified compiled bundle: {exc}") from exc
    if not result.get("workflow"):
        raise InterventionError("Compiled run has no workflow blueprint")
    return result, manifest


def _read_workflow(run_directory: Path) -> dict[str, Any]:
    path = run_directory.resolve() / "artifacts" / "workflow.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InterventionError(f"Cannot read compiled workflow: {path}") from exc
    if value.get("contract") != "agent-workflow-compiled/v1":
        raise InterventionError("Compiled workflow contract is invalid")
    return value


def _workflow_nodes(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_nodes = workflow.get("workflow", {}).get("nodes")
    if not isinstance(raw_nodes, list):
        raise InterventionError("Compiled workflow node registry is invalid")
    return {node["id"]: node for node in raw_nodes if isinstance(node, dict) and "id" in node}


def _read_markers(path: Path, *, expected_run_id: str) -> list[tuple[int, dict[str, str]]]:
    markers: list[tuple[int, dict[str, str]]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise InterventionError(f"Cannot read run event stream: {path}") from exc
    for line_number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InterventionError(f"Invalid run event JSON on line {line_number}") from exc
        if event.get("type") != INTERVENTION_EVENT:
            continue
        marker = event.get("summary")
        if not isinstance(marker, dict) or set(marker) != MARKER_FIELDS:
            raise InterventionError(f"Invalid intervention marker on event line {line_number}")
        try:
            marker = InterventionMarker.model_validate(marker).model_dump(mode="json")
        except ValidationError as exc:
            raise InterventionError(
                f"Invalid intervention contract on event line {line_number}"
            ) from exc
        if marker.get("run_id") != expected_run_id:
            raise InterventionError(f"Intervention run ID mismatch on event line {line_number}")
        if event.get("target") != marker.get("graph_node"):
            raise InterventionError(f"Intervention node mismatch on event line {line_number}")
        if not all(isinstance(marker[field], str) and marker[field] for field in MARKER_FIELDS):
            raise InterventionError(f"Incomplete intervention marker on event line {line_number}")
        markers.append((line_number, marker))
    return markers


def _node_pointer(workflow: dict[str, Any], node_id: str) -> str:
    nodes = workflow["workflow"]["nodes"]
    index = next(index for index, node in enumerate(nodes) if node.get("id") == node_id)
    return f"/workflow/nodes/{index}"


def _node_resource_ids(node: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    for key, value in node.items():
        if key.endswith("_resource") and isinstance(value, str):
            values.add(value)
        elif (key.endswith("_resources") or key == "resource_ids") and isinstance(value, list):
            values.update(item for item in value if isinstance(item, str))
    return sorted(values)


def _session_source(session_log: Path | None) -> dict[str, Any] | None:
    if session_log is None:
        return None
    resolved = session_log.resolve()
    if not resolved.is_file():
        raise InterventionError(f"Session log does not exist: {resolved}")
    try:
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise InterventionError(f"Cannot read session log: {resolved}") from exc
    return {"pointer": _file_pointer(resolved), "lines": lines}


def _session_window(
    session_source: dict[str, Any] | None,
    anchor: str,
    radius: int,
) -> dict[str, Any] | None:
    if session_source is None:
        return None
    lines = session_source["lines"]
    matches = []
    for index, line in enumerate(lines, start=1):
        if anchor in line:
            matches.append(
                {
                    "anchor_line": index,
                    "start_line": max(1, index - radius),
                    "end_line": min(len(lines), index + radius),
                }
            )
    return {
        "path": session_source["pointer"]["path"],
        "anchor": anchor,
        "matches": matches,
    }


def _git_bookmark(repo: Path, marker_head: str, collection_head: str) -> dict[str, Any]:
    if not _git_succeeds(repo, "cat-file", "-e", f"{marker_head}^{{commit}}"):
        raise InterventionError(f"Intervention Git commit is unavailable: {marker_head}")
    relationship = "same"
    nearest_descendant = None
    diff_range = None
    if marker_head != collection_head:
        is_ancestor = (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", marker_head, collection_head],
                cwd=repo,
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
        if is_ancestor:
            relationship = "ancestor"
            commits = _git(
                repo,
                "rev-list",
                "--ancestry-path",
                "--reverse",
                f"{marker_head}..{collection_head}",
            ).splitlines()
            nearest_descendant = commits[0] if commits else None
            diff_range = f"{marker_head}..{collection_head}"
        else:
            relationship = "diverged"
    return {
        "repository": str(repo),
        "marker_head": marker_head,
        "collection_head": collection_head,
        "relationship": relationship,
        "nearest_descendant": nearest_descendant,
        "diff_range": diff_range,
    }


def _git_head(repository: Path) -> str:
    return _git(_repository_root(repository), "rev-parse", "HEAD")


def _repository_root(repository: Path) -> Path:
    candidate = repository.resolve()
    root = _git(candidate, "rev-parse", "--show-toplevel", allow_failure=True)
    if not root:
        raise InterventionError(f"Not a Git repository: {candidate}")
    return Path(root).resolve()


def _git(repo: Path, *arguments: str, allow_failure: bool = False) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise InterventionError("Git could not be executed") from exc
    if completed.returncode != 0:
        if allow_failure:
            return ""
        detail = (completed.stderr or completed.stdout).strip()
        raise InterventionError(f"Git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def _git_succeeds(repo: Path, *arguments: str) -> bool:
    try:
        return (
            subprocess.run(
                ["git", *arguments],
                cwd=repo,
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
    except OSError as exc:
        raise InterventionError("Git could not be executed") from exc


def _file_pointer(path: Path) -> dict[str, Any]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise InterventionError(f"Cannot read audit source: {path}") from exc
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()
