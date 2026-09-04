---
name: agent-workflow-execution
description: Execute a verified FormalPrompt workflow blueprint while preserving intent and logging physical deviations.
license: MIT
---

# Agent Workflow Execution

Consume a compiled agent-workflow-compiled/v1 blueprint as the authoritative execution plan. Preserve the approved graph, spend context only on ready work, and distinguish planned intent from runtime evidence.

## When to Use

- formalprompt result returns a verified result containing workflow and execution_contract paths.
- The user asks Codex to carry out an approved node graph.
- A resumed project needs to determine the next ready nodes without replaying initialization dialogue.
- Do not execute an uncompiled, unapproved, or unverifiable canvas document.

## Procedure

1. Run formalprompt result against the run directory and stop if verification rejects the bundle.
2. Read the declared execution_contract and workflow files. Do not load the facilitator transcript, request queue, or event ledger unless an audit or unresolved decision requires it.
3. Verify agent-workflow-compiled/v1, the approved document digest, resource hashes, capability versions, entry nodes, completion nodes, and global policy.
4. Determine readiness from incoming ports and recorded evidence. Run only nodes whose required inputs are satisfied. An all join waits for every declared input edge. An any join proceeds on its first successful input and cancels every remaining upstream branch at that join; cancellation is terminal but not success. Respect maximum_parallel_nodes.
5. For an agent node, provide only its referenced prompt, agent definition, context, skills, and tools. Enforce its write scope, timeout, budget, and acceptance criteria.
6. For an operation, review, or gate, require the evidence named by the node. Treat an empty operation write scope as read-only and enforce every nonempty scope. A checkpoint may mutate Git only through its pinned git-checkpoint capability. Never infer a pass from process exit, file presence, or a model's unsupported claim.
7. If physical reality invalidates an implementation detail, preserve the intended outcome, make the narrowest viable adaptation allowed by workflow.policy.deviation, and append a deviation record with the triggering evidence, affected node, old assumption, chosen change, and verification.
8. Never silently edit the approved graph. A consequential authority, scope, model, completion, or intent change requires the policy's user-approval path.
9. For failed review, instantiate a new forward-only repair attempt from the review node's remediation template. Preserve each attempt and stop at maximum_rounds; follow the declared exhaustion policy.
10. Complete only when every declared completion node has satisfied inputs and its acceptance evidence is durable.

## Evidence Record

For each attempt retain at least:

- workflow and node IDs;
- attempt number, status, start/end time, and responsible agent/model;
- input and output resource digests;
- commands or external checkpoints used;
- bounded verification evidence;
- deviations and their causal rationale;
- review findings, repair ancestry, and user decisions.

Runtime evidence is append-only. Git diffs may show implementation changes, but they do not replace causal records.

## Pitfalls

- Do not treat topological display order as permission to ignore typed inputs.
- Do not widen write scope because a task seems convenient.
- Do not collapse review and repair attempts into one overwritten status.
- Do not ask the primary context to rediscover facts already pinned in node resources.
- Do not redefine completion when checks fail; repair, escalate, or halt according to policy.

## Verification

- The compiled bundle passes FormalPrompt's strict result verifier.
- Every completed node has its required inputs and acceptance evidence.
- Every adaptation is attributable and the approved graph is unchanged.
- Review attempts remain independent and bounded.
- All declared completion nodes are satisfied before project completion is reported.
