from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel

from formalprompt.models import CanvasDocument, CanvasField

ARTIFACT_PATH_PATTERN = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")


class ValidationIssue(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str
    field_id: str | None = None


def validate_document(document: dict[str, Any] | CanvasDocument) -> list[ValidationIssue]:
    model = (
        document
        if isinstance(document, CanvasDocument)
        else CanvasDocument.model_validate(document)
    )
    issues: list[ValidationIssue] = []
    seen_tabs: set[str] = set()
    seen_sections: set[str] = set()
    seen_fields: set[str] = set()

    for tab in model.tabs:
        if tab.id in seen_tabs:
            issues.append(_issue("duplicate-tab-id", f"Duplicate tab ID: {tab.id}"))
        seen_tabs.add(tab.id)
        for section in tab.sections:
            if section.id in seen_sections:
                issues.append(_issue("duplicate-section-id", f"Duplicate section ID: {section.id}"))
            seen_sections.add(section.id)
            for field in section.fields:
                if field.id in seen_fields:
                    issues.append(
                        _issue(
                            "duplicate-field-id",
                            f"Duplicate field ID: {field.id}",
                            field.id,
                        )
                    )
                seen_fields.add(field.id)
                issues.extend(_validate_field(field))
    issues.extend(_validate_initialization(model))
    return issues


def is_ready(document: dict[str, Any] | CanvasDocument) -> bool:
    model = (
        document
        if isinstance(document, CanvasDocument)
        else CanvasDocument.model_validate(document)
    )
    return not model.completion.require_independent_review and not any(
        issue.severity == "error" for issue in validate_document(model)
    )


def independent_review_issue() -> ValidationIssue:
    return _issue(
        "independent-review-required",
        "The current revision requires a passing independent review",
    )


def validate_field_candidate(field: CanvasField, value: Any) -> list[ValidationIssue]:
    candidate = field.model_copy(deep=True)
    candidate.value = value
    candidate.provenance = "user-confirmed"
    candidate.review_status = "accepted"
    return _validate_field(candidate)


def _validate_field(field: CanvasField) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    missing = field.value is None or field.value == "" or field.value == []
    if field.required and missing:
        issues.append(
            _issue(
                "required-value-missing",
                f"{field.label} requires a value",
                field.id,
            )
        )
    if field.importance == "blocker" and (
        field.provenance == "unresolved" or field.review_status in {"needs-input", "conflict"}
    ):
        issues.append(
            _issue(
                "unresolved-blocker",
                f"{field.label} must be resolved before approval",
                field.id,
            )
        )
    elif field.review_status == "conflict":
        issues.append(_issue("field-conflict", f"{field.label} contains a conflict", field.id))

    option_list = [option.value for option in field.options]
    option_values = set(option_list)
    if field.type in {"select", "multiselect"} and not option_list:
        issues.append(_issue("missing-options", f"{field.label} has no options", field.id))
    if len(option_values) != len(option_list):
        issues.append(_issue("duplicate-option", f"{field.label} has duplicate options", field.id))

    if field.type == "select" and not missing:
        if not isinstance(field.value, str):
            issues.append(
                _issue("invalid-type", f"{field.label} must be an option value", field.id)
            )
            issues.append(
                _issue("invalid-option", f"{field.label} has an invalid option", field.id)
            )
        elif field.value not in option_values:
            issues.append(
                _issue("invalid-option", f"{field.label} has an invalid option", field.id)
            )
    if field.type == "multiselect" and not missing:
        valid_list = isinstance(field.value, list) and all(
            isinstance(value, str) for value in field.value
        )
        if not valid_list:
            issues.append(
                _issue("invalid-type", f"{field.label} must be a list of option values", field.id)
            )
        if not valid_list or any(value not in option_values for value in field.value):
            issues.append(_issue("invalid-option", f"{field.label} has invalid options", field.id))
    if (
        field.type in {"text", "textarea"}
        and field.value is not None
        and not isinstance(field.value, str)
    ):
        issues.append(_issue("invalid-type", f"{field.label} must be text", field.id))
    if field.type == "checkbox" and not isinstance(field.value, bool):
        issues.append(_issue("invalid-type", f"{field.label} must be true or false", field.id))
    if (
        field.type == "number"
        and field.value is not None
        and (isinstance(field.value, bool) or not isinstance(field.value, (int, float)))
    ):
        issues.append(_issue("invalid-type", f"{field.label} must be a number", field.id))

    rules = field.validation
    compiled_pattern = None
    if rules.pattern is not None:
        try:
            compiled_pattern = re.compile(rules.pattern)
        except re.error:
            issues.append(
                _issue("invalid-pattern", f"{field.label} has an invalid pattern", field.id)
            )
    if (
        rules.min_length is not None
        and rules.max_length is not None
        and rules.min_length > rules.max_length
    ):
        issues.append(
            _issue(
                "invalid-length-range", f"{field.label} has inconsistent length limits", field.id
            )
        )
    if rules.minimum is not None and rules.maximum is not None and rules.minimum > rules.maximum:
        issues.append(
            _issue(
                "invalid-number-range", f"{field.label} has inconsistent numeric limits", field.id
            )
        )

    if isinstance(field.value, str):
        if rules.min_length is not None and len(field.value) < rules.min_length:
            issues.append(_issue("min-length", f"{field.label} is too short", field.id))
        if rules.max_length is not None and len(field.value) > rules.max_length:
            issues.append(_issue("max-length", f"{field.label} is too long", field.id))
        if compiled_pattern is not None and compiled_pattern.fullmatch(field.value) is None:
            issues.append(_issue("pattern", f"{field.label} has an invalid format", field.id))
    if isinstance(field.value, (int, float)) and not isinstance(field.value, bool):
        if rules.minimum is not None and field.value < rules.minimum:
            issues.append(_issue("minimum", f"{field.label} is below its minimum", field.id))
        if rules.maximum is not None and field.value > rules.maximum:
            issues.append(_issue("maximum", f"{field.label} exceeds its maximum", field.id))
    return issues


def _validate_initialization(document: CanvasDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    artifacts = document.initialization.artifacts
    for artifact in artifacts:
        if artifact.id in seen_ids:
            issues.append(_issue("duplicate-artifact-id", f"Duplicate artifact ID: {artifact.id}"))
        seen_ids.add(artifact.id)
        normalized_path = PurePosixPath(artifact.path)
        if (
            ARTIFACT_PATH_PATTERN.fullmatch(artifact.path) is None
            or "\\" in artifact.path
            or normalized_path.is_absolute()
            or any(part in {"", ".", ".."} for part in normalized_path.parts)
            or any(part.casefold() in {".git", ".formalprompt"} for part in normalized_path.parts)
        ):
            issues.append(
                _issue(
                    "unsafe-artifact-path",
                    f"{artifact.title} must use a safe relative POSIX path",
                )
            )
        canonical = normalized_path.as_posix().casefold()
        if canonical in seen_paths:
            issues.append(
                _issue("duplicate-artifact-path", f"Duplicate artifact path: {artifact.path}")
            )
        seen_paths.add(canonical)
        if not artifact.content.strip() and artifact.importance in {"blocker", "high"}:
            issues.append(_issue("artifact-content-missing", f"{artifact.title} requires content"))
        if artifact.importance == "blocker" and (
            artifact.provenance == "unresolved"
            or artifact.review_status in {"needs-input", "conflict", "rejected"}
        ):
            issues.append(
                _issue("unresolved-artifact", f"{artifact.title} must be resolved before approval")
            )
        elif artifact.review_status == "conflict":
            issues.append(_issue("artifact-conflict", f"{artifact.title} contains a conflict"))
    primary = document.initialization.primary_artifact
    if primary is not None and primary not in seen_ids:
        issues.append(
            _issue(
                "unknown-primary-artifact",
                f"Primary initialization artifact does not exist: {primary}",
            )
        )
    return issues


def _issue(code: str, message: str, field_id: str | None = None) -> ValidationIssue:
    return ValidationIssue(code=code, severity="error", message=message, field_id=field_id)
