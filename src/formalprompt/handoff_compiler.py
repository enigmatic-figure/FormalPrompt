from __future__ import annotations

from typing import Any

from formalprompt.models import CanvasDocument


def specification_markdown(document: CanvasDocument) -> str:
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
                        display_value(field.value),
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


def execution_brief(document: CanvasDocument) -> str:
    lines = [
        f"# Execution Brief: {document.metadata.title}",
        "",
        document.metadata.description,
        "",
        "## Confirmed specification",
        "",
    ]
    for field in document.fields():
        lines.append(f"- **{field.label}:** {display_value(field.value)}")
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


def display_value(value: Any) -> str:
    if value is None or value == "" or value == []:
        return "_Not specified_"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)
