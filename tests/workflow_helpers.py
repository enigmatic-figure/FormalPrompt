from __future__ import annotations

from tests.test_session_api import minimal_document


def workflow_document() -> dict:
    document = minimal_document()
    document["initialization"] = {
        "primary_artifact": "prompt.implement",
        "artifacts": [
            _artifact("prompt.implement", "prompts/IMPLEMENT.md", "primary-prompt", "Implement"),
            _artifact("agent.codex", "agents/CODEX.agent.md", "agent-definition", "Agent"),
            _artifact("prompt.verify", "prompts/VERIFY.md", "primary-prompt", "Verify"),
            _artifact("prompt.review", "prompts/REVIEW.md", "primary-prompt", "Review"),
            _artifact("prompt.handoff", "prompts/HANDOFF.md", "primary-prompt", "Handoff"),
            _artifact(
                "template.repair",
                "templates/REPAIR.md",
                "workflow-template",
                "Repair",
            ),
        ],
    }
    document["workflow"] = {
        "protocol": "agent-workflow/v1",
        "title": "Validated implementation",
        "description": "Implement, verify, review, approve, and hand off.",
        "resources": [
            _resource("prompt.implement", "prompt", "prompt.implement"),
            _resource("agent.codex", "agent-definition", "agent.codex"),
            _resource("prompt.verify", "prompt", "prompt.verify"),
            _resource("prompt.review", "prompt", "prompt.review"),
            _resource("prompt.handoff", "prompt", "prompt.handoff"),
            _resource("template.repair", "template", "template.repair"),
            {
                "id": "tool.terminal",
                "kind": "tool",
                "title": "Terminal",
                "binding": "harness-capability",
                "reference": "terminal",
                "version": "codex-runtime/v1",
                "availability_check": "execution-preflight",
            },
        ],
        "nodes": [
            {
                **_node("intent", "input", 40, 180),
                "resource_ids": ["prompt.implement"],
                "output_ports": [_port("next", "Start", "control")],
            },
            {
                **_node("implement", "agent", 300, 180),
                "model": "codex",
                "prompt_resource": "prompt.implement",
                "agent_definition_resource": "agent.codex",
                "tool_resources": ["tool.terminal"],
                "write_scope": ["src/**", "tests/**"],
                "acceptance_criteria": ["Requested behavior is implemented"],
                "input_ports": [_port("start", "Start", "control", required=True)],
                "output_ports": [_port("next", "Implemented", "control")],
            },
            {
                **_node("verify", "operation", 560, 180),
                "operation": "test",
                "instruction_resource": "prompt.verify",
                "resource_ids": ["tool.terminal"],
                "write_scope": [],
                "acceptance_criteria": ["All configured checks pass"],
                "input_ports": [_port("start", "Implementation", "control", required=True)],
                "output_ports": [
                    _port("next", "Verified", "control"),
                    _port("evidence", "Evidence", "evidence"),
                ],
            },
            {
                **_node("review", "review", 820, 180),
                "model": "chatgpt-5.6-sol-high",
                "prompt_resource": "prompt.review",
                "subject_resources": ["prompt.implement", "agent.codex"],
                "required_evidence": ["Verification results", "Immutable Git commit"],
                "independent": True,
                "independent_from": ["implement"],
                "remediation": {
                    "maximum_rounds": 5,
                    "repair_template_resource": "template.repair",
                    "exhaustion": "request-user-decision",
                },
                "input_ports": [
                    _port("work", "Work", "control", required=True),
                    _port("evidence", "Evidence", "evidence", required=True),
                ],
                "output_ports": [_port("next", "Passed", "control")],
            },
            {
                **_node("approve", "gate", 1080, 180),
                "gate": "user-approval",
                "criteria": ["User affirms the reviewed workflow result"],
                "required_evidence": ["Independent review pass"],
                "input_ports": [_port("reviewed", "Reviewed", "control", required=True)],
                "output_ports": [_port("next", "Approved", "control")],
            },
            {
                **_node("handoff", "operation", 1340, 180),
                "operation": "handoff",
                "instruction_resource": "prompt.handoff",
                "write_scope": ["delivery/**"],
                "acceptance_criteria": ["Verified execution artifacts are handed off"],
                "input_ports": [_port("approved", "Approved", "control", required=True)],
            },
        ],
        "edges": [
            _edge("intent-implement", "intent", "next", "implement", "start", "control"),
            _edge("implement-verify", "implement", "next", "verify", "start", "control"),
            _edge("verify-review", "verify", "next", "review", "work", "control"),
            _edge("evidence-review", "verify", "evidence", "review", "evidence", "evidence"),
            _edge("review-approve", "review", "next", "approve", "reviewed", "control"),
            _edge("approve-handoff", "approve", "next", "handoff", "approved", "control"),
        ],
        "entry_nodes": ["intent"],
        "completion_nodes": ["handoff"],
        "policy": {
            "maximum_parallel_nodes": 4,
            "failure": "pause-for-user",
            "deviation": "log-and-adapt",
        },
    }
    return document


def _artifact(identifier: str, path: str, kind: str, title: str) -> dict:
    return {
        "id": identifier,
        "path": path,
        "kind": kind,
        "title": title,
        "content": f"# {title}\n\nFollow the approved workflow.\n",
        "provenance": "proposed",
        "review_status": "accepted",
        "importance": "high",
    }


def _resource(identifier: str, kind: str, artifact_id: str) -> dict:
    return {
        "id": identifier,
        "kind": kind,
        "title": identifier,
        "binding": "initialization-artifact",
        "reference": artifact_id,
    }


def _node(identifier: str, kind: str, x: float, y: float) -> dict:
    return {
        "id": identifier,
        "kind": kind,
        "title": identifier.replace("-", " ").title(),
        "position": {"x": x, "y": y},
        "provenance": "proposed",
        "review_status": "accepted",
    }


def _port(identifier: str, label: str, data_type: str, *, required: bool = False) -> dict:
    return {
        "id": identifier,
        "label": label,
        "data_type": data_type,
        "required": required,
    }


def _edge(
    identifier: str,
    source_node: str,
    source_port: str,
    target_node: str,
    target_port: str,
    data_type: str,
) -> dict:
    return {
        "id": identifier,
        "source_node": source_node,
        "source_port": source_port,
        "target_node": target_node,
        "target_port": target_port,
        "data_type": data_type,
    }
