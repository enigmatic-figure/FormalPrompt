from __future__ import annotations

from typing import Annotated, Any, Literal

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
        "tool-definition",
        "workflow-template",
        "execution-policy",
        "report-template",
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


class GraphPosition(StrictModel):
    x: float = Field(ge=0, le=100_000)
    y: float = Field(ge=0, le=100_000)


class WorkflowPort(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    label: str = Field(min_length=1)
    data_type: Literal["control", "context", "artifact", "evidence"]
    required: bool = False
    multiple: bool = False


class WorkflowResource(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    kind: Literal[
        "prompt",
        "agent-definition",
        "skill",
        "tool",
        "template",
        "knowledge",
        "policy",
        "report-template",
    ]
    title: str = Field(min_length=1)
    binding: Literal["initialization-artifact", "harness-capability"]
    reference: str = Field(min_length=1)
    version: str | None = None
    availability_check: Literal["execution-preflight"] | None = None
    description: str = ""


class WorkflowNodeBase(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    title: str = Field(min_length=1)
    description: str = ""
    position: GraphPosition
    input_ports: list[WorkflowPort] = Field(default_factory=list)
    output_ports: list[WorkflowPort] = Field(default_factory=list)
    provenance: Literal["explicit", "inferred", "proposed", "user-confirmed", "unresolved"]
    review_status: Literal["unreviewed", "accepted", "rejected", "needs-input", "conflict"]
    importance: Literal["blocker", "high", "normal", "low"] = "normal"
    rationale: str = ""


class InputWorkflowNode(WorkflowNodeBase):
    kind: Literal["input"]
    resource_ids: list[str] = Field(default_factory=list)


class ArtifactWorkflowNode(WorkflowNodeBase):
    kind: Literal["artifact"]
    resource_id: str
    mode: Literal["read", "produce", "transform"] = "read"


class AgentWorkflowNode(WorkflowNodeBase):
    kind: Literal["agent"]
    model: str = Field(min_length=1)
    prompt_resource: str
    agent_definition_resource: str | None = None
    context_resources: list[str] = Field(default_factory=list)
    skill_resources: list[str] = Field(default_factory=list)
    tool_resources: list[str] = Field(default_factory=list)
    write_scope: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1)
    timeout_seconds: int = Field(default=3600, ge=1, le=86_400)
    token_budget: int | None = Field(default=None, ge=1)


class OperationWorkflowNode(WorkflowNodeBase):
    kind: Literal["operation"]
    operation: Literal[
        "research",
        "test",
        "report",
        "materialize",
        "checkpoint",
        "handoff",
    ]
    instruction_resource: str
    resource_ids: list[str] = Field(default_factory=list)
    write_scope: list[str]
    acceptance_criteria: list[str] = Field(min_length=1)
    timeout_seconds: int = Field(default=3600, ge=1, le=86_400)


class RemediationPolicy(StrictModel):
    maximum_rounds: int = Field(default=3, ge=1, le=20)
    repair_template_resource: str
    exhaustion: Literal["block", "request-user-decision"] = "block"


class ReviewWorkflowNode(WorkflowNodeBase):
    kind: Literal["review"]
    model: str = Field(min_length=1)
    prompt_resource: str
    subject_resources: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(min_length=1)
    independent: Literal[True] = True
    independent_from: list[str] = Field(default_factory=list)
    remediation: RemediationPolicy


class GateWorkflowNode(WorkflowNodeBase):
    kind: Literal["gate"]
    gate: Literal["user-approval", "verification", "policy"]
    criteria: list[str] = Field(min_length=1)
    required_evidence: list[str] = Field(default_factory=list)


class JoinWorkflowNode(WorkflowNodeBase):
    kind: Literal["join"]
    strategy: Literal["all", "any"] = "all"
    remaining_branches: Literal["cancel"] | None = None


WorkflowNode = Annotated[
    InputWorkflowNode
    | ArtifactWorkflowNode
    | AgentWorkflowNode
    | OperationWorkflowNode
    | ReviewWorkflowNode
    | GateWorkflowNode
    | JoinWorkflowNode,
    Field(discriminator="kind"),
]


class WorkflowEdge(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    source_node: str
    source_port: str
    target_node: str
    target_port: str
    data_type: Literal["control", "context", "artifact", "evidence"]
    label: str = ""


class WorkflowPolicy(StrictModel):
    maximum_parallel_nodes: int = Field(default=4, ge=1, le=64)
    failure: Literal["halt", "pause-for-user"] = "halt"
    deviation: Literal["log-and-adapt", "require-user-approval"] = "log-and-adapt"


class WorkflowGraph(StrictModel):
    protocol: Literal["agent-workflow/v1"]
    title: str = Field(min_length=1)
    description: str = ""
    resources: list[WorkflowResource] = Field(default_factory=list)
    nodes: list[WorkflowNode] = Field(min_length=1)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    entry_nodes: list[str] = Field(min_length=1)
    completion_nodes: list[str] = Field(min_length=1)
    policy: WorkflowPolicy = Field(default_factory=WorkflowPolicy)


class CanvasDocument(StrictModel):
    protocol: Literal["agent-canvas/v1"]
    kind: Literal["formalprompt/specification"]
    metadata: Metadata
    tabs: list[Tab] = Field(min_length=1)
    completion: Completion = Field(default_factory=Completion)
    initialization: InitializationPlan = Field(default_factory=InitializationPlan)
    workflow: WorkflowGraph | None = None

    def fields(self) -> list[CanvasField]:
        return [field for tab in self.tabs for section in tab.sections for field in section.fields]
