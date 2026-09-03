from __future__ import annotations

import hashlib
import json
import shutil
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any

from formalprompt.artifacts import (
    ArtifactBundleError,
    verify_compiled_run,
    verify_staged_compilation,
)
from formalprompt.handoff_compiler import execution_brief, specification_markdown
from formalprompt.integrity import document_sha256
from formalprompt.store import RevisionConflict, RunStore
from formalprompt.workflow_compiler import compile_workflow_payloads


class ApprovalRequired(Exception):
    pass


def recover_interrupted_compilation(store: RunStore) -> str:
    """Finalize a complete staged bundle or restore an interrupted run to approved."""
    state = store.read_state()
    if state.get("status") != "compiling":
        return "unchanged"
    revision = state["revision"]
    try:
        verify_staged_compilation(store.path)
    except (ArtifactBundleError, OSError, ValueError):
        _discard_staged_compilation(store, revision)
        store.append_event(
            "compilation.recovered",
            "system",
            None,
            {"revision": revision, "action": "restored-approved"},
        )
        return "restored-approved"
    store.mark_compiled(revision)
    store.append_event(
        "compilation.recovered",
        "system",
        None,
        {"revision": revision, "action": "finalized-compiled"},
    )
    return "finalized-compiled"


def load_verified_result(store: RunStore) -> dict[str, Any]:
    recover_interrupted_compilation(store)
    result, _ = verify_compiled_run(store.path)
    return result


def compile_run(store: RunStore, expected_revision: int) -> dict[str, Any]:
    try:
        approval = store.begin_compilation(expected_revision)
    except RevisionConflict as exc:
        raise ApprovalRequired(str(exc)) from exc

    try:
        document = store.read_document()
        approved_document_sha256 = document_sha256(document)
        if approval.get("document_sha256") != approved_document_sha256:
            raise ApprovalRequired("The compiled document does not match the approved contents")
        artifacts = store.path / "artifacts"
        artifacts.mkdir(exist_ok=True)

        payloads: dict[str, str] = {
            "specification.json": json.dumps(
                document.model_dump(mode="json"), ensure_ascii=False, indent=2
            )
            + "\n",
            "SPECIFICATION.md": specification_markdown(document),
            "EXECUTION_BRIEF.md": execution_brief(document),
            "approval.json": json.dumps(approval, ensure_ascii=False, indent=2) + "\n",
        }
        artifact_paths: dict[str, str] = {}
        compiled_paths = {name.casefold() for name in payloads}
        for artifact in document.initialization.artifacts:
            relative = f"initialization/{PurePosixPath(artifact.path).as_posix()}"
            canonical_relative = relative.casefold()
            if canonical_relative in compiled_paths:
                raise ValueError(f"Duplicate compiled artifact path: {relative}")
            compiled_paths.add(canonical_relative)
            payloads[relative] = (
                artifact.content if artifact.content.endswith("\n") else artifact.content + "\n"
            )
            artifact_paths[artifact.id] = relative
        workflow_payloads = compile_workflow_payloads(
            document,
            document_digest=approved_document_sha256,
            artifact_paths=artifact_paths,
            artifact_payloads=payloads,
        )
        for name, content in workflow_payloads.items():
            canonical_name = name.casefold()
            if canonical_name in compiled_paths:
                raise ValueError(f"Duplicate compiled workflow artifact path: {name}")
            compiled_paths.add(canonical_name)
            payloads[name] = content
        for name, content in payloads.items():
            destination = _artifact_destination(artifacts, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(destination, content)

        files: dict[str, dict[str, Any]] = {}
        for name in sorted(payloads):
            data = _artifact_destination(artifacts, name).read_bytes()
            files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        manifest = {
            "contract": "agent-canvas-manifest/v1",
            "run_id": store.run_id,
            "revision": expected_revision,
            "document_sha256": approved_document_sha256,
            "files": files,
        }
        _atomic_write(
            artifacts / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )

        unresolved_count = sum(field.provenance == "unresolved" for field in document.fields())
        unresolved_count += sum(
            artifact.provenance == "unresolved" for artifact in document.initialization.artifacts
        )
        primary = document.initialization.primary_artifact
        handoff = (
            f"artifacts/{artifact_paths[primary]}"
            if primary is not None
            else "artifacts/EXECUTION_BRIEF.md"
        )
        result = {
            "contract": "agent-canvas-result/v1",
            "run_id": store.run_id,
            "status": "compiled",
            "revision": expected_revision,
            "document_sha256": approved_document_sha256,
            "unresolved_count": unresolved_count,
            "artifacts": files,
            "handoff": handoff,
        }
        if document.workflow is not None:
            result["workflow"] = "artifacts/workflow.json"
            result["execution_contract"] = "artifacts/EXECUTION_CONTRACT.md"
        _atomic_write(
            store.path / "result.json",
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        )
        store.mark_compiled(expected_revision)
        return result
    except Exception:
        with suppress(OSError):
            _discard_staged_compilation(store, expected_revision)
        raise


def _discard_staged_compilation(store: RunStore, revision: int) -> None:
    artifacts = store.path / "artifacts"
    if artifacts.exists():
        shutil.rmtree(artifacts)
    for partial in (store.path / "result.json", store.path / "result.json.tmp"):
        partial.unlink(missing_ok=True)
    store.abort_compilation(revision)


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _artifact_destination(root: Path, relative: str) -> Path:
    destination = root.joinpath(*PurePosixPath(relative).parts).resolve()
    destination.relative_to(root.resolve())
    return destination
