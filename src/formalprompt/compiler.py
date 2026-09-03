from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any

from formalprompt.store import RevisionConflict, RunStore


class ApprovalRequired(Exception):
    pass


def compile_run(store: RunStore, expected_revision: int) -> dict[str, Any]:
    try:
        approval = store.begin_compilation(expected_revision)
    except RevisionConflict as exc:
        raise ApprovalRequired(str(exc)) from exc

    try:
        document = store.read_document()
        artifacts = store.path / "artifacts"
        artifacts.mkdir(exist_ok=True)

        payloads: dict[str, str] = {
            "specification.json": json.dumps(
                document.model_dump(mode="json"), ensure_ascii=False, indent=2
            )
            + "\n",
            "SPECIFICATION.md": _specification_markdown(document),
            "EXECUTION_BRIEF.md": _execution_brief(document),
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
            "unresolved_count": unresolved_count,
            "artifacts": files,
            "handoff": handoff,
        }
        _atomic_write(
            store.path / "result.json",
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        )
        store.mark_compiled(expected_revision)
        return result
    except Exception:
        with suppress(OSError):
            store.abort_compilation(expected_revision)
        raise


def _specification_markdown(document) -> str:
    lines = [
        f"# {document.metadata.title}",
        "",
        document.metadata.description,
        "",
    ]
    for tab in document.tabs:
        lines.extend([f"## {tab.label}", ""])
        if tab.description:
            lines.extend([tab.description, ""])
        for section in tab.sections:
            lines.extend([f"### {section.title}", ""])
            if section.description:
                lines.extend([section.description, ""])
            for field in section.fields:
                lines.extend(
                    [
                        f"#### {field.label}",
                        "",
                        _display_value(field.value),
                        "",
                        f"Provenance: {field.provenance}",
                        f"Review status: {field.review_status}",
                        f"Importance: {field.importance}",
                    ]
                )
                if field.rationale:
                    lines.append(f"Rationale: {field.rationale}")
                lines.append("")
    if document.initialization.artifacts:
        lines.extend(["## Initialization artifacts", ""])
        for artifact in document.initialization.artifacts:
            lines.extend(
                [
                    f"### {artifact.title}",
                    "",
                    f"Path: `{artifact.path}`",
                    f"Kind: {artifact.kind}",
                    f"Provenance: {artifact.provenance}",
                    f"Review status: {artifact.review_status}",
                    "",
                    artifact.content,
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _execution_brief(document) -> str:
    lines = [
        f"# Execution Brief: {document.metadata.title}",
        "",
        document.metadata.description,
        "",
        "## Confirmed specification",
        "",
    ]
    for field in document.fields():
        lines.append(f"- **{field.label}:** {_display_value(field.value)}")
    if document.initialization.artifacts:
        lines.extend(["", "## Initialization package", ""])
        for artifact in document.initialization.artifacts:
            lines.append(
                f"- **{artifact.title}** ({artifact.kind}): `initialization/{artifact.path}`"
            )
    lines.extend(
        [
            "",
            "## Execution contract",
            "",
            "Implement against the confirmed values above. Treat blocker and high-importance "
            "fields as constraints. Verify the resulting work against this specification before "
            "reporting completion.",
            "",
        ]
    )
    return "\n".join(lines)


def _display_value(value: Any) -> str:
    if value is None or value == "" or value == []:
        return "_Not specified_"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _artifact_destination(root: Path, relative: str) -> Path:
    destination = root.joinpath(*PurePosixPath(relative).parts).resolve()
    destination.relative_to(root.resolve())
    return destination
