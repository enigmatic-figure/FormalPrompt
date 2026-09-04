from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from formalprompt.handoff_compiler import execution_brief, specification_markdown
from formalprompt.integrity import document_sha256
from formalprompt.models import CanvasDocument
from formalprompt.workflow_compiler import compile_workflow_payloads


class ArtifactBundleError(RuntimeError):
    pass


def verify_compiled_run(run_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return _verify_bundle(run_directory, allowed_statuses={"compiled"})


def verify_staged_compilation(run_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return _verify_bundle(run_directory, allowed_statuses={"compiling"})


def _verify_bundle(
    run_directory: Path, *, allowed_statuses: set[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_root = run_directory.resolve()
    state = _read_json(run_root / "state.json")
    document = _read_json(run_root / "document.json")
    result = _read_json(run_root / "result.json")
    manifest = _read_json(run_root / "artifacts" / "manifest.json")
    approval = _read_json(run_root / "artifacts" / "approval.json")
    if state.get("status") not in allowed_statuses:
        expected = " or ".join(sorted(allowed_statuses))
        raise ArtifactBundleError(f"Run state is not {expected}")
    if result.get("contract") != "agent-canvas-result/v1" or result.get("status") != "compiled":
        raise ArtifactBundleError("Run result is not a compiled Agent Canvas result")
    if manifest.get("contract") != "agent-canvas-manifest/v1":
        raise ArtifactBundleError("Artifact manifest contract is not recognized")
    state_approval = state.get("approval")
    if not isinstance(state_approval, dict) or state_approval != approval:
        raise ArtifactBundleError("Durable state approval does not match the compiled approval")
    revisions = [
        state.get("revision"),
        state_approval.get("revision"),
        result.get("revision"),
        manifest.get("revision"),
        approval.get("revision"),
    ]
    if (
        not isinstance(revisions[0], int)
        or isinstance(revisions[0], bool)
        or any(revision != revisions[0] for revision in revisions[1:])
    ):
        raise ArtifactBundleError("Result, manifest, and approval revisions do not match")
    specification = _read_json(run_root / "artifacts" / "specification.json")
    try:
        document_model = CanvasDocument.model_validate(document)
        current_document_digest = document_sha256(document)
        specification_digest = document_sha256(specification)
    except (TypeError, ValueError) as exc:
        raise ArtifactBundleError("Compiled specification is not a valid canvas document") from exc
    digests = [
        current_document_digest,
        specification_digest,
        state_approval.get("document_sha256"),
        approval.get("document_sha256"),
        result.get("document_sha256"),
        manifest.get("document_sha256"),
    ]
    if (
        not isinstance(digests[0], str)
        or len(digests[0]) != 64
        or any(digest != digests[0] for digest in digests[1:])
    ):
        raise ArtifactBundleError("Approved, current, and compiled document digests do not match")

    run_ids = [state.get("run_id"), result.get("run_id"), manifest.get("run_id")]
    if not isinstance(run_ids[0], str) or any(run_id != run_ids[0] for run_id in run_ids[1:]):
        raise ArtifactBundleError("State, result, and manifest run IDs do not match")

    artifacts_root = (run_root / "artifacts").resolve()
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ArtifactBundleError("Artifact manifest files must be an object")
    for relative, metadata in files.items():
        if not isinstance(relative, str) or not isinstance(metadata, dict):
            raise ArtifactBundleError("Artifact manifest entries must map paths to metadata")
        source = _contained_path(artifacts_root, relative)
        if not source.is_file():
            raise ArtifactBundleError(f"Declared artifact is missing: {relative}")
        content = source.read_bytes()
        if metadata.get("bytes") != len(content):
            raise ArtifactBundleError(f"Artifact size does not match manifest: {relative}")
        file_digest = hashlib.sha256(content).hexdigest()
        if metadata.get("sha256") != file_digest:
            raise ArtifactBundleError(f"Artifact hash does not match manifest: {relative}")
    actual_files = {
        path.relative_to(artifacts_root).as_posix()
        for path in artifacts_root.rglob("*")
        if path.is_file() and path != artifacts_root / "manifest.json"
    }
    if actual_files != set(files):
        raise ArtifactBundleError("Artifact manifest does not exactly declare the compiled bundle")
    artifact_paths, artifact_payloads, expected_files = _expected_payloads(document_model)
    if document_model.workflow is not None:
        expected_files.update({"workflow.json", "EXECUTION_CONTRACT.md"})
    if set(files) != expected_files:
        raise ArtifactBundleError(
            "Artifact manifest membership does not match the approved document"
        )
    _verify_derived_payloads(
        artifacts_root,
        document_model,
        digests[0],
        artifact_paths,
        artifact_payloads,
    )
    if result.get("artifacts") != files:
        raise ArtifactBundleError("Run result artifact metadata does not match the manifest")
    handoff = result.get("handoff")
    if not isinstance(handoff, str) or not handoff.startswith("artifacts/"):
        raise ArtifactBundleError("Run result does not declare a valid handoff")
    if handoff.removeprefix("artifacts/") not in files:
        raise ArtifactBundleError("Run handoff is not declared by the artifact manifest")
    workflow_path = result.get("workflow")
    execution_contract = result.get("execution_contract")
    has_workflow = document_model.workflow is not None
    if has_workflow != (workflow_path is not None or execution_contract is not None):
        raise ArtifactBundleError("Run workflow declaration does not match the approved document")
    if has_workflow:
        if workflow_path != "artifacts/workflow.json":
            raise ArtifactBundleError("Run workflow path is not recognized")
        if execution_contract != "artifacts/EXECUTION_CONTRACT.md":
            raise ArtifactBundleError("Run execution contract path is not recognized")
        if "workflow.json" not in files or "EXECUTION_CONTRACT.md" not in files:
            raise ArtifactBundleError("Compiled workflow files are not declared by the manifest")
        compiled_workflow = _read_json(artifacts_root / "workflow.json")
        if compiled_workflow.get("contract") != "agent-workflow-compiled/v1":
            raise ArtifactBundleError("Compiled workflow contract is not recognized")
        if compiled_workflow.get("document_sha256") != digests[0]:
            raise ArtifactBundleError("Compiled workflow document digest does not match approval")
        if compiled_workflow.get("workflow") != document.get("workflow"):
            raise ArtifactBundleError("Compiled workflow does not match the approved blueprint")
        _verify_workflow_resources(compiled_workflow, files)
    return result, manifest


def _expected_payloads(
    document: CanvasDocument,
) -> tuple[dict[str, str], dict[str, str], set[str]]:
    artifact_paths: dict[str, str] = {}
    artifact_payloads: dict[str, str] = {}
    expected_files = {
        "specification.json",
        "SPECIFICATION.md",
        "EXECUTION_BRIEF.md",
        "approval.json",
    }
    for artifact in document.initialization.artifacts:
        relative = f"initialization/{PurePosixPath(artifact.path).as_posix()}"
        artifact_paths[artifact.id] = relative
        artifact_payloads[relative] = (
            artifact.content if artifact.content.endswith("\n") else artifact.content + "\n"
        )
        expected_files.add(relative)
    return artifact_paths, artifact_payloads, expected_files


def _verify_derived_payloads(
    artifacts_root: Path,
    document: CanvasDocument,
    document_digest: str,
    artifact_paths: dict[str, str],
    artifact_payloads: dict[str, str],
) -> None:
    expected = {
        "SPECIFICATION.md": specification_markdown(document),
        "EXECUTION_BRIEF.md": execution_brief(document),
        **artifact_payloads,
    }
    expected.update(
        compile_workflow_payloads(
            document,
            document_digest=document_digest,
            artifact_paths=artifact_paths,
            artifact_payloads=artifact_payloads,
        )
    )
    for relative, content in expected.items():
        if _contained_path(artifacts_root, relative).read_text(encoding="utf-8") != content:
            raise ArtifactBundleError(
                f"Compiled artifact does not match the approved document: {relative}"
            )


def materialize_initialization(
    run_directory: Path, destination: Path, *, force: bool = False
) -> list[Path]:
    _, manifest = verify_compiled_run(run_directory)
    artifacts_root = (run_directory.resolve() / "artifacts").resolve()
    destination_root = destination.resolve()
    initialization = [
        relative for relative in manifest["files"] if relative.startswith("initialization/")
    ]
    if not initialization:
        raise ArtifactBundleError("Compiled run contains no initialization artifacts")

    targets: list[tuple[Path, Path]] = []
    for relative in initialization:
        project_relative = relative.removeprefix("initialization/")
        source = _contained_path(artifacts_root, relative)
        target = _contained_path(destination_root, project_relative)
        if target.exists() and not force:
            raise ArtifactBundleError(f"Refusing to replace existing project file: {target}")
        targets.append((source, target))

    transaction_id = uuid4().hex
    prepared: list[tuple[Path, Path]] = []
    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    try:
        for source, target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            staged = target.with_name(f".{target.name}.formalprompt-{transaction_id}.new")
            staged.write_bytes(source.read_bytes())
            prepared.append((staged, target))
        for staged, target in prepared:
            if target.exists():
                backup = target.with_name(f".{target.name}.formalprompt-{transaction_id}.bak")
                target.replace(backup)
                backups[target] = backup
            staged.replace(target)
            installed.append(target)
    except OSError as exc:
        rollback_errors: list[str] = []
        for target in reversed(installed):
            try:
                target.unlink(missing_ok=True)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        for target, backup in backups.items():
            try:
                if backup.exists():
                    backup.replace(target)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if rollback_errors:
            raise ArtifactBundleError(
                "Initialization materialization failed and rollback was incomplete; "
                "transaction backup files were retained"
            ) from exc
        raise ArtifactBundleError("Initialization materialization could not be committed") from exc
    finally:
        for staged, _ in prepared:
            staged.unlink(missing_ok=True)
    for backup in backups.values():
        backup.unlink(missing_ok=True)
    return installed


def _contained_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(part.casefold() in {".git", ".formalprompt"} for part in path.parts)
    ):
        raise ArtifactBundleError(f"Unsafe artifact path: {relative}")
    destination = root.joinpath(*path.parts).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ArtifactBundleError(f"Artifact path escapes its root: {relative}") from exc
    return destination


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactBundleError(f"Cannot read required artifact metadata: {path}") from exc
    if not isinstance(value, dict):
        raise ArtifactBundleError(f"Artifact metadata must be an object: {path}")
    return value


def _verify_workflow_resources(
    compiled_workflow: dict[str, Any], files: dict[str, dict[str, Any]]
) -> None:
    resources = compiled_workflow.get("resolved_resources")
    if not isinstance(resources, dict):
        raise ArtifactBundleError("Compiled workflow resource registry is invalid")
    for resource_id, resolution in resources.items():
        if not isinstance(resource_id, str) or not isinstance(resolution, dict):
            raise ArtifactBundleError("Compiled workflow resource entry is invalid")
        binding = resolution.get("binding")
        if binding == "initialization-artifact":
            path = resolution.get("path")
            if not isinstance(path, str) or path not in files:
                raise ArtifactBundleError(f"Workflow resource is not manifested: {resource_id}")
            if resolution.get("sha256") != files[path].get("sha256"):
                raise ArtifactBundleError(f"Workflow resource digest does not match: {resource_id}")
        elif binding == "harness-capability":
            if (
                not resolution.get("capability")
                or not resolution.get("version")
                or resolution.get("availability_check") != "execution-preflight"
            ):
                raise ArtifactBundleError(f"Workflow capability is not pinned: {resource_id}")
        else:
            raise ArtifactBundleError(f"Workflow resource binding is invalid: {resource_id}")
