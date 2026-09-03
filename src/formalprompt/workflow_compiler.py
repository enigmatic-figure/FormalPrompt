from __future__ import annotations

import hashlib
import json
from typing import Any

from formalprompt.models import CanvasDocument, WorkflowGraph


def compile_workflow_payloads(
    document: CanvasDocument,
    *,
    document_digest: str,
    artifact_paths: dict[str, str],
    artifact_payloads: dict[str, str],
) -> dict[str, str]:
    graph = document.workflow
    if graph is None:
        return {}
    resolved_resources: dict[str, dict[str, Any]] = {}
    for resource in graph.resources:
        if resource.binding == "initialization-artifact":
            path = artifact_paths[resource.reference]
            content = artifact_payloads[path].encode("utf-8")
            resolved_resources[resource.id] = {
                "kind": resource.kind,
                "binding": resource.binding,
                "artifact_id": resource.reference,
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        else:
            resolved_resources[resource.id] = {
                "kind": resource.kind,
                "binding": resource.binding,
                "capability": resource.reference,
                "version": resource.version,
            }
    compiled = {
        "contract": "agent-workflow-compiled/v1",
        "document_sha256": document_digest,
        "workflow": graph.model_dump(mode="json"),
        "resolved_resources": resolved_resources,
    }
    return {
        "workflow.json": json.dumps(compiled, ensure_ascii=False, indent=2) + "\n",
        "EXECUTION_CONTRACT.md": _execution_contract(graph, resolved_resources),
    }


def _execution_contract(graph: WorkflowGraph, resolved_resources: dict[str, dict[str, Any]]) -> str:
    incoming: dict[str, list[str]] = {node.id: [] for node in graph.nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        incoming[edge.target_node].append(edge.source_node)
        outgoing[edge.source_node].append(edge.target_node)
    order = _topological_order(graph)
    nodes = {node.id: node for node in graph.nodes}
    lines = [
        f"# Execution Contract: {graph.title}",
        "",
        graph.description,
        "",
        "## Runtime invariants",
        "",
        "- `artifacts/workflow.json` is the authoritative approved blueprint.",
        "- Execute a node only when its required incoming ports are satisfied.",
        "- Never widen a node's declared resources, tools, write scope, or authority silently.",
        "- Record physical deviations and adaptations as execution evidence; do not rewrite the "
        "approved graph.",
        "- A review retry creates a new forward-only attempt from its remediation policy.",
        "",
        f"Maximum parallel nodes: {graph.policy.maximum_parallel_nodes}",
        f"Failure policy: {graph.policy.failure}",
        f"Deviation policy: {graph.policy.deviation}",
        "",
        "## Resource registry",
        "",
    ]
    for resource_id, resolution in resolved_resources.items():
        lines.append(f"- `{resource_id}`: `{json.dumps(resolution, ensure_ascii=False)}`")
    lines.extend(["", "## Topological execution order", ""])
    for index, node_id in enumerate(order, start=1):
        node = nodes[node_id]
        dependencies = ", ".join(f"`{item}`" for item in incoming[node_id]) or "_entry_"
        enabled = ", ".join(f"`{item}`" for item in outgoing[node_id]) or "_completion_"
        lines.extend(
            [
                f"### {index}. {node.title} (`{node.id}`)",
                "",
                f"- Kind: `{node.kind}`",
                f"- Depends on: {dependencies}",
                f"- Enables: {enabled}",
                f"- Importance: `{node.importance}`",
                f"- Provenance: `{node.provenance}`",
                f"- Review status: `{node.review_status}`",
                "",
                "```json",
                json.dumps(node.model_dump(mode="json"), ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _topological_order(graph: WorkflowGraph) -> list[str]:
    indegree = {node.id: 0 for node in graph.nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        indegree[edge.target_node] += 1
        outgoing[edge.source_node].append(edge.target_node)
    ready = [node.id for node in graph.nodes if indegree[node.id] == 0]
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    return order
