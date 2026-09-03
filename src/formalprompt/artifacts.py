from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any


class ArtifactBundleError(RuntimeError):
    pass


def verify_compiled_run(run_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_root = run_directory.resolve()
    result = _read_json(run_root / "result.json")
    manifest = _read_json(run_root / "artifacts" / "manifest.json")
    approval = _read_json(run_root / "artifacts" / "approval.json")
    if result.get("contract") != "agent-canvas-result/v1" or result.get("status") != "compiled":
        raise ArtifactBundleError("Run result is not a compiled Agent Canvas result")
    if manifest.get("contract") != "agent-canvas-manifest/v1":
        raise ArtifactBundleError("Artifact manifest contract is not recognized")
    revisions = {result.get("revision"), manifest.get("revision"), approval.get("revision")}
    if len(revisions) != 1:
        raise ArtifactBundleError("Result, manifest, and approval revisions do not match")

    artifacts_root = (run_root / "artifacts").resolve()
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ArtifactBundleError("Artifact manifest files must be an object")
    for relative, metadata in files.items():
        source = _contained_path(artifacts_root, relative)
        if not source.is_file():
            raise ArtifactBundleError(f"Declared artifact is missing: {relative}")
        content = source.read_bytes()
        if metadata.get("bytes") != len(content):
            raise ArtifactBundleError(f"Artifact size does not match manifest: {relative}")
        digest = hashlib.sha256(content).hexdigest()
        if metadata.get("sha256") != digest:
            raise ArtifactBundleError(f"Artifact hash does not match manifest: {relative}")
    return result, manifest


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

    written: list[Path] = []
    for source, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(source.read_bytes())
        temporary.replace(target)
        written.append(target)
    return written


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
