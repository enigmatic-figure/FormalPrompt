from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metadata(StrictModel):
    title: str = Field(min_length=1)
    description: str = ""
    created_by: str = Field(min_length=1)


class Option(StrictModel):
    value: str
    label: str
    implications: str = ""


class FieldValidation(StrictModel):
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=0)
    pattern: str | None = Field(
        default=None,
        max_length=512,
        description="Server-enforced RE2 full-match pattern; never executed by the browser.",
    )
    minimum: float | None = None
    maximum: float | None = None


class Assistance(StrictModel):
    enabled: bool = False
    prompt: str = ""


class CanvasField(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    label: str = Field(min_length=1)
    type: Literal["text", "textarea", "number", "checkbox", "select", "multiselect"]
    value: Any = None
    description: str = ""
    placeholder: str = ""
    required: bool = False
    importance: Literal["blocker", "high", "normal", "low"] = "normal"
    provenance: Literal["explicit", "inferred", "proposed", "user-confirmed", "unresolved"]
    review_status: Literal["unreviewed", "accepted", "rejected", "needs-input", "conflict"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    rationale: str = ""
    options: list[Option] = Field(default_factory=list)
    validation: FieldValidation = Field(default_factory=FieldValidation)
    assistance: Assistance = Field(default_factory=Assistance)


class Section(StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    fields: list[CanvasField] = Field(min_length=1)


class Tab(StrictModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = ""
    sections: list[Section] = Field(min_length=1)


class Completion(StrictModel):
    require_user_approval: Literal[True] = True
    require_independent_review: bool = False


class InitializationArtifact(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    path: str = Field(min_length=1)
    kind: Literal[
        "primary-prompt",
        "agent-definition",
        "skill",
        "research-request",
        "knowledge-base-plan",
        "project-plan",
        "other",
    ]
    title: str = Field(min_length=1)
    content: str
    description: str = ""
    provenance: Literal["explicit", "inferred", "proposed", "user-confirmed", "unresolved"]
    review_status: Literal["unreviewed", "accepted", "rejected", "needs-input", "conflict"]
    importance: Literal["blocker", "high", "normal", "low"] = "normal"
    rationale: str = ""


class InitializationPlan(StrictModel):
    primary_artifact: str | None = None
    artifacts: list[InitializationArtifact] = Field(default_factory=list)


class CanvasDocument(StrictModel):
    protocol: Literal["agent-canvas/v1"]
    kind: Literal["formalprompt/specification"]
    metadata: Metadata
    tabs: list[Tab] = Field(min_length=1)
    completion: Completion = Field(default_factory=Completion)
    initialization: InitializationPlan = Field(default_factory=InitializationPlan)

    def fields(self) -> list[CanvasField]:
        return [field for tab in self.tabs for section in tab.sections for field in section.fields]
