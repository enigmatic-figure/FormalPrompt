from __future__ import annotations

import math
from pathlib import PurePosixPath
from typing import Any, Literal

import re2
from pydantic import BaseModel

from formalprompt.models import (
    AgentWorkflowNode,
    ArtifactWorkflowNode,
    CanvasDocument,
    CanvasField,
    InputWorkflowNode,
    JoinWorkflowNode,
    OperationWorkflowNode,
    ReviewWorkflowNode,
    WorkflowGraph,
)

RE2_OPTIONS = re2.Options()
RE2_OPTIONS.log_errors = False
RE2_OPTIONS.max_mem = 8 * 1024 * 1024
ARTIFACT_PATH_PATTERN = re2.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*", options=RE2_OPTIONS)


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
    if model.workflow is not None:
        issues.extend(_validate_workflow(model))
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
    if (
        field.type == "number"
        and isinstance(field.value, (int, float))
        and not isinstance(field.value, bool)
        and not math.isfinite(field.value)
    ):
        issues.append(_issue("non-finite-number", f"{field.label} must be finite", field.id))

    rules = field.validation
    compiled_pattern = None
    if rules.pattern is not None:
        try:
            compiled_pattern = re2.compile(rules.pattern, options=RE2_OPTIONS)
        except re2.error:
            issues.append(
                _issue("invalid-pattern", f"{field.label} is not a valid RE2 pattern", field.id)
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


def _validate_workflow(document: CanvasDocument) -> list[ValidationIssue]:
    graph = document.workflow
    assert graph is not None
    issues: list[ValidationIssue] = []
    resources = _unique_map(
        [(resource.id, resource) for resource in graph.resources],
        "duplicate-workflow-resource-id",
        "workflow resource",
        issues,
    )
    nodes = _unique_map(
        [(node.id, node) for node in graph.nodes],
        "duplicate-workflow-node-id",
        "workflow node",
        issues,
    )
    _unique_map(
        [(edge.id, edge) for edge in graph.edges],
        "duplicate-workflow-edge-id",
        "workflow edge",
        issues,
    )
    artifacts = {artifact.id: artifact for artifact in document.initialization.artifacts}
    for resource in graph.resources:
        if resource.binding == "initialization-artifact":
            if resource.availability_check is not None:
                issues.append(
                    _issue(
                        "artifact-availability-check-invalid",
                        f"Initialization artifact {resource.title} cannot declare a runtime "
                        "availability check",
                        resource.id,
                    )
                )
            artifact = artifacts.get(resource.reference)
            if artifact is None:
                issues.append(
                    _issue(
                        "unknown-workflow-artifact",
                        f"Workflow resource {resource.title} references an unknown "
                        "initialization artifact",
                        resource.id,
                    )
                )
            elif not _artifact_resource_compatible(artifact.kind, resource.kind):
                issues.append(
                    _issue(
                        "incompatible-workflow-artifact",
                        f"Workflow resource {resource.title} declares kind {resource.kind} but "
                        f"artifact {resource.reference} has kind {artifact.kind}",
                        resource.id,
                    )
                )
        else:
            if not resource.version:
                issues.append(
                    _issue(
                        "unpinned-workflow-capability",
                        f"Harness capability {resource.title} requires a version",
                        resource.id,
                    )
                )
            if resource.availability_check != "execution-preflight":
                issues.append(
                    _issue(
                        "capability-preflight-missing",
                        f"Harness capability {resource.title} must be resolved during "
                        "execution preflight",
                        resource.id,
                    )
                )

    incoming: dict[str, list] = {node_id: [] for node_id in nodes}
    outgoing: dict[str, list] = {node_id: [] for node_id in nodes}
    input_ports: dict[str, dict] = {}
    output_ports: dict[str, dict] = {}
    for node in graph.nodes:
        input_ports[node.id] = _port_map(node.id, "input", node.input_ports, issues)
        output_ports[node.id] = _port_map(node.id, "output", node.output_ports, issues)
        if node.provenance == "unresolved" or node.review_status in {
            "needs-input",
            "conflict",
            "rejected",
        }:
            issues.append(
                _issue(
                    "unresolved-workflow-node",
                    f"Workflow node {node.title} must be resolved before approval",
                    node.id,
                )
            )
        issues.extend(_validate_node_resources(node, resources))
        if isinstance(node, (AgentWorkflowNode, OperationWorkflowNode)):
            for scope in node.write_scope:
                if not _safe_scope(scope):
                    issues.append(
                        _issue(
                            "unsafe-agent-write-scope",
                            f"Writer node {node.title} has unsafe write scope: {scope}",
                            node.id,
                        )
                    )
        if isinstance(node, OperationWorkflowNode):
            issues.extend(_validate_operation_authority(node, resources))
        if isinstance(node, JoinWorkflowNode):
            issues.extend(_validate_join(node))

    for edge in graph.edges:
        source = nodes.get(edge.source_node)
        target = nodes.get(edge.target_node)
        if source is None:
            issues.append(
                _issue(
                    "unknown-edge-source",
                    f"Workflow edge {edge.id} has an unknown source node",
                    edge.id,
                )
            )
        if target is None:
            issues.append(
                _issue(
                    "unknown-edge-target",
                    f"Workflow edge {edge.id} has an unknown target node",
                    edge.id,
                )
            )
        source_port = output_ports.get(edge.source_node, {}).get(edge.source_port)
        target_port = input_ports.get(edge.target_node, {}).get(edge.target_port)
        if source is not None and source_port is None:
            issues.append(
                _issue(
                    "unknown-edge-source-port",
                    f"Workflow edge {edge.id} has an unknown source port",
                    edge.id,
                )
            )
        if target is not None and target_port is None:
            issues.append(
                _issue(
                    "unknown-edge-target-port",
                    f"Workflow edge {edge.id} has an unknown target port",
                    edge.id,
                )
            )
        if source_port is not None and source_port.data_type != edge.data_type:
            issues.append(
                _issue(
                    "edge-source-type-mismatch",
                    f"Workflow edge {edge.id} does not match its source port type",
                    edge.id,
                )
            )
        if target_port is not None and target_port.data_type != edge.data_type:
            issues.append(
                _issue(
                    "edge-target-type-mismatch",
                    f"Workflow edge {edge.id} does not match its target port type",
                    edge.id,
                )
            )
        if source is not None and target is not None:
            outgoing[source.id].append(edge)
            incoming[target.id].append(edge)

    issues.extend(_validate_required_ports(graph, incoming))
    issues.extend(_validate_join_sources(graph, incoming))
    issues.extend(_validate_graph_paths(graph, nodes, incoming, outgoing))
    issues.extend(_validate_review_independence(graph, nodes, incoming))
    issues.extend(_validate_parallel_write_scopes(graph, incoming, outgoing))
    return issues


def _unique_map(items, code: str, label: str, issues: list[ValidationIssue]) -> dict:
    result = {}
    for identifier, value in items:
        if identifier in result:
            issues.append(_issue(code, f"Duplicate {label} ID: {identifier}", identifier))
        result[identifier] = value
    return result


def _port_map(node_id: str, direction: str, ports: list, issues: list[ValidationIssue]) -> dict:
    result = {}
    for port in ports:
        if port.id in result:
            issues.append(
                _issue(
                    "duplicate-workflow-port-id",
                    f"Workflow node {node_id} has duplicate {direction} port {port.id}",
                    node_id,
                )
            )
        result[port.id] = port
    return result


def _validate_node_resources(node, resources: dict) -> list[ValidationIssue]:
    references: list[tuple[str, set[str] | None]] = []
    if isinstance(node, InputWorkflowNode):
        references.extend((reference, None) for reference in node.resource_ids)
    elif isinstance(node, ArtifactWorkflowNode):
        references.append((node.resource_id, None))
    elif isinstance(node, AgentWorkflowNode):
        references.append((node.prompt_resource, {"prompt"}))
        if node.agent_definition_resource:
            references.append((node.agent_definition_resource, {"agent-definition"}))
        references.extend((reference, None) for reference in node.context_resources)
        references.extend((reference, {"skill"}) for reference in node.skill_resources)
        references.extend((reference, {"tool"}) for reference in node.tool_resources)
    elif isinstance(node, OperationWorkflowNode):
        references.append((node.instruction_resource, {"prompt", "policy", "template"}))
        references.extend((reference, None) for reference in node.resource_ids)
    elif isinstance(node, ReviewWorkflowNode):
        references.append((node.prompt_resource, {"prompt"}))
        references.append((node.remediation.repair_template_resource, {"template", "prompt"}))
        references.extend((reference, None) for reference in node.subject_resources)

    issues: list[ValidationIssue] = []
    for reference, allowed_kinds in references:
        resource = resources.get(reference)
        if resource is None:
            issues.append(
                _issue(
                    "unknown-node-resource",
                    f"Workflow node {node.title} references unknown resource {reference}",
                    node.id,
                )
            )
        elif allowed_kinds is not None and resource.kind not in allowed_kinds:
            issues.append(
                _issue(
                    "incompatible-node-resource",
                    f"Workflow node {node.title} cannot use {resource.kind} "
                    f"resource {reference} here",
                    node.id,
                )
            )
    return issues


def _artifact_resource_compatible(artifact_kind: str, resource_kind: str) -> bool:
    compatible = {
        "primary-prompt": {"prompt"},
        "agent-definition": {"agent-definition"},
        "skill": {"skill"},
        "research-request": {"prompt", "knowledge"},
        "knowledge-base-plan": {"knowledge"},
        "project-plan": {"prompt", "policy"},
        "tool-definition": {"tool"},
        "workflow-template": {"template"},
        "execution-policy": {"policy"},
        "report-template": {"report-template", "template"},
        "other": set(),
    }
    return resource_kind in compatible[artifact_kind]


def _validate_operation_authority(node, resources: dict) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if node.operation in {"materialize", "report", "handoff"} and not node.write_scope:
        issues.append(
            _issue(
                "mutating-operation-scope-missing",
                f"Operation node {node.title} must declare a write scope",
                node.id,
            )
        )
    if node.operation == "checkpoint":
        capabilities = {
            resource.reference
            for resource_id in node.resource_ids
            if (resource := resources.get(resource_id)) is not None
            and resource.binding == "harness-capability"
        }
        if "git-checkpoint" not in capabilities:
            issues.append(
                _issue(
                    "checkpoint-capability-missing",
                    f"Checkpoint node {node.title} requires a pinned git-checkpoint capability",
                    node.id,
                )
            )
        if node.write_scope:
            issues.append(
                _issue(
                    "checkpoint-write-scope-forbidden",
                    f"Checkpoint node {node.title} must use the bounded git-checkpoint "
                    "capability instead of a filesystem write scope",
                    node.id,
                )
            )
    return issues


def _validate_join(node: JoinWorkflowNode) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if len(node.input_ports) < 2:
        issues.append(
            _issue(
                "join-input-count",
                f"Join node {node.title} requires at least two branch inputs",
                node.id,
            )
        )
    if any(
        port.data_type != "control" or not port.required or port.multiple
        for port in node.input_ports
    ):
        issues.append(
            _issue(
                "join-input-contract",
                f"Join node {node.title} inputs must be required, single-cardinality control ports",
                node.id,
            )
        )
    if any(port.data_type != "control" for port in node.output_ports):
        issues.append(
            _issue(
                "join-output-contract",
                f"Join node {node.title} outputs must be control ports",
                node.id,
            )
        )
    if node.strategy == "any" and node.remaining_inputs != "ignore":
        issues.append(
            _issue(
                "join-any-input-policy-missing",
                f"Any-join node {node.title} must ignore later successful inputs",
                node.id,
            )
        )
    if node.strategy == "all" and node.remaining_inputs is not None:
        issues.append(
            _issue(
                "join-all-input-policy-invalid",
                f"All-join node {node.title} cannot declare a remaining-input policy",
                node.id,
            )
        )
    return issues


def _validate_required_ports(
    graph: WorkflowGraph, incoming: dict[str, list]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for node in graph.nodes:
        for port in node.input_ports:
            count = sum(edge.target_port == port.id for edge in incoming[node.id])
            if port.required and count == 0:
                issues.append(
                    _issue(
                        "required-workflow-input-missing",
                        f"Workflow node {node.title} requires input port {port.label}",
                        node.id,
                    )
                )
            if not port.multiple and count > 1:
                issues.append(
                    _issue(
                        "workflow-input-cardinality",
                        f"Workflow node {node.title} input {port.label} accepts only one edge",
                        node.id,
                    )
                )
    return issues


def _validate_join_sources(
    graph: WorkflowGraph, incoming: dict[str, list]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for node in graph.nodes:
        if not isinstance(node, JoinWorkflowNode):
            continue
        sources = [edge.source_node for edge in incoming[node.id]]
        if len(sources) != len(set(sources)):
            issues.append(
                _issue(
                    "join-duplicate-branch-source",
                    f"Join node {node.title} requires distinct source branches",
                    node.id,
                )
            )
    return issues


def _validate_graph_paths(
    graph, nodes: dict, incoming: dict, outgoing: dict
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    entries = set(graph.entry_nodes)
    completions = set(graph.completion_nodes)
    for node_id in entries:
        if node_id not in nodes:
            issues.append(_issue("unknown-entry-node", f"Unknown workflow entry node: {node_id}"))
        elif incoming[node_id]:
            issues.append(
                _issue("entry-node-has-input", f"Workflow entry node {node_id} has incoming edges")
            )
    for node_id in completions:
        if node_id not in nodes:
            issues.append(
                _issue("unknown-completion-node", f"Unknown workflow completion node: {node_id}")
            )
        elif outgoing[node_id]:
            issues.append(
                _issue(
                    "completion-node-has-output",
                    f"Workflow completion node {node_id} has outgoing edges",
                )
            )

    indegree = {node_id: len(incoming[node_id]) for node_id in nodes}
    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited: list[str] = []
    while queue:
        node_id = queue.pop()
        visited.append(node_id)
        for edge in outgoing[node_id]:
            indegree[edge.target_node] -= 1
            if indegree[edge.target_node] == 0:
                queue.append(edge.target_node)
    if len(visited) != len(nodes):
        issues.append(_issue("workflow-cycle", "Workflow graph must be acyclic"))
        return issues

    reachable = _reachable(entries & nodes.keys(), outgoing, forward=True)
    for node_id in nodes.keys() - reachable:
        issues.append(
            _issue(
                "workflow-node-unreachable",
                f"Workflow node {node_id} is not reachable from a declared entry",
                node_id,
            )
        )
    reaches_completion = _reachable(completions & nodes.keys(), incoming, forward=False)
    for node_id in nodes.keys() - reaches_completion:
        issues.append(
            _issue(
                "workflow-node-no-completion-path",
                f"Workflow node {node_id} cannot reach a declared completion",
                node_id,
            )
        )
    return issues


def _reachable(starts, adjacency: dict, *, forward: bool) -> set[str]:
    found = set(starts)
    pending = list(starts)
    while pending:
        node_id = pending.pop()
        for edge in adjacency[node_id]:
            neighbor = edge.target_node if forward else edge.source_node
            if neighbor not in found:
                found.add(neighbor)
                pending.append(neighbor)
    return found


def _validate_review_independence(
    graph: WorkflowGraph, nodes: dict, incoming: dict
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for node in graph.nodes:
        if not isinstance(node, ReviewWorkflowNode):
            continue
        declared = set(node.independent_from)
        for agent_id in declared:
            if not isinstance(nodes.get(agent_id), AgentWorkflowNode):
                issues.append(
                    _issue(
                        "invalid-review-independence-reference",
                        f"Review node {node.title} declares non-agent {agent_id} as an "
                        "independence subject",
                        node.id,
                    )
                )
        ancestors = _reachable({node.id}, incoming, forward=False) - {node.id}
        upstream_agents = {
            node_id for node_id in ancestors if isinstance(nodes[node_id], AgentWorkflowNode)
        }
        missing = sorted(upstream_agents - declared)
        if missing:
            issues.append(
                _issue(
                    "review-independence-incomplete",
                    f"Review node {node.title} must declare independence from upstream agents: "
                    f"{', '.join(missing)}",
                    node.id,
                )
            )
    return issues


def _validate_parallel_write_scopes(
    graph: WorkflowGraph, incoming: dict, outgoing: dict
) -> list[ValidationIssue]:
    writers = [
        node
        for node in graph.nodes
        if isinstance(node, (AgentWorkflowNode, OperationWorkflowNode)) and node.write_scope
    ]
    must_precede = _must_predecessors(graph, incoming, outgoing)
    issues: list[ValidationIssue] = []
    for index, left in enumerate(writers):
        for right in writers[index + 1 :]:
            ordered = left.id in must_precede[right.id] or right.id in must_precede[left.id]
            if not ordered and any(
                _scopes_overlap(left_scope, right_scope)
                for left_scope in left.write_scope
                for right_scope in right.write_scope
            ):
                issues.append(
                    _issue(
                        "overlapping-parallel-write-scope",
                        f"Parallel writer nodes {left.title} and {right.title} "
                        "have overlapping write scope",
                    )
                )
    return issues


def _must_predecessors(graph: WorkflowGraph, incoming: dict, outgoing: dict) -> dict[str, set[str]]:
    """Return nodes that must finish before each node can become ready.

    Ordinary nodes and all-joins require every connected required input. An any-join
    can proceed through any one input, so only predecessors common to every branch
    are guaranteed to finish before it. Invalid or cyclic graphs remain conservative:
    validation reports those errors separately and unresolved ordering never suppresses
    a write-scope collision.
    """

    nodes = {node.id: node for node in graph.nodes}
    indegree = {node_id: len(incoming[node_id]) for node_id in nodes}
    pending = [node_id for node_id, degree in indegree.items() if degree == 0]
    must_precede = {node_id: set() for node_id in nodes}
    while pending:
        node_id = pending.pop()
        node = nodes[node_id]
        branch_dependencies = [
            {edge.source_node, *must_precede[edge.source_node]}
            for edge in incoming[node_id]
            if edge.source_node in nodes
        ]
        if isinstance(node, JoinWorkflowNode) and node.strategy == "any":
            if branch_dependencies:
                must_precede[node_id] = set.intersection(*branch_dependencies)
        else:
            required_ports = {port.id for port in node.input_ports if port.required}
            required_dependencies = [
                {edge.source_node, *must_precede[edge.source_node]}
                for edge in incoming[node_id]
                if edge.source_node in nodes and edge.target_port in required_ports
            ]
            if required_dependencies:
                must_precede[node_id] = set.union(*required_dependencies)
        for edge in outgoing[node_id]:
            if edge.target_node not in indegree:
                continue
            indegree[edge.target_node] -= 1
            if indegree[edge.target_node] == 0:
                pending.append(edge.target_node)
    return must_precede


def _safe_scope(scope: str) -> bool:
    return _parse_scope(scope) is not None


def _scopes_overlap(left: str, right: str) -> bool:
    left_parsed = _parse_scope(left)
    right_parsed = _parse_scope(right)
    if left_parsed is None or right_parsed is None:
        return True
    left_parts, left_recursive = left_parsed
    right_parts, right_recursive = right_parsed
    if not left_recursive and not right_recursive and len(left_parts) != len(right_parts):
        return False
    if left_recursive and not right_recursive and len(right_parts) < len(left_parts):
        return False
    if right_recursive and not left_recursive and len(left_parts) < len(right_parts):
        return False
    candidate_length = max(len(left_parts), len(right_parts))
    for index in range(candidate_length):
        left_part = left_parts[index] if index < len(left_parts) else "*"
        right_part = right_parts[index] if index < len(right_parts) else "*"
        if left_part != "*" and right_part != "*" and left_part != right_part:
            return False
    return True


def _parse_scope(scope: str) -> tuple[tuple[str, ...], bool] | None:
    path = PurePosixPath(scope)
    if not scope or "\\" in scope or path.is_absolute():
        return None
    parts = tuple(scope.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        return None
    if not parts or parts[0] in {"*", "**"}:
        return None
    recursive = parts[-1] == "**"
    ordinary = parts[:-1] if recursive else parts
    for part in ordinary:
        if part in {"", ".", "..", "**"}:
            return None
        if part == "*":
            continue
        if (
            not ARTIFACT_PATH_PATTERN.fullmatch(part)
            or any(character in part for character in "?[]{}!")
            or part.casefold() in {".git", ".formalprompt"}
        ):
            return None
    return tuple(part.casefold() for part in ordinary), recursive


def _issue(code: str, message: str, field_id: str | None = None) -> ValidationIssue:
    return ValidationIssue(code=code, severity="error", message=message, field_id=field_id)
