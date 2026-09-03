---
name: agent-workflow-authoring
description: Compose a typed FormalPrompt agent workflow DAG and its referenced initialization artifacts.
license: MIT
---

# Agent Workflow Authoring

Compose a user-auditable agent-workflow/v1 DAG inside a FormalPrompt canvas. Treat the graph as a declarative blueprint of authority and intent: it identifies work, dependencies, resources, checkpoints, and completion evidence but executes nothing.

## When to Use

- A project needs multiple agents, phases, review checkpoints, or explicit context distribution.
- The user wants to inspect or manipulate the proposed development process as a node graph.
- An initialization-compose request is ready for a durable workflow rather than another clarification canvas.
- Do not use this skill to execute nodes or modify the target project.

## Procedure

1. Preserve every explicit and user-confirmed specification fact. Mark defensible interpretations inferred, recommendations proposed, and consequential unknowns unresolved.
2. Create the prompts, agent definitions, skills, tool descriptions, policies, report templates, and knowledge plans actually needed as typed initialization artifacts. Keep each artifact role-scoped.
3. Register every artifact or harness capability used by a node in workflow resources. Bind generated files by artifact ID. Bind runtime capabilities by stable capability name and an explicit version.
4. Build nodes from the smallest adequate types: input, artifact, agent, operation, review, gate, and join. Give every agent its exact model, prompt, context, tools, skills, write scope, budget where known, and observable acceptance criteria.
5. Connect nodes through declared typed ports. Use control for sequencing, context for bounded input, artifact for produced material, and evidence for verification or review proof.
6. Keep the declared graph acyclic. Put bounded repair behavior in a review node's remediation policy; a runtime may instantiate forward-only repair attempts without rewriting the approved graph.
7. Include explicit test, independent-review, user-approval, report, checkpoint, and handoff nodes whenever the specification requires them. A review node must identify evidence and declare every upstream agent in independent_from.
8. Set entry and completion nodes, choose parallelism/failure/deviation policies, and ensure every node is reachable from an entry and can reach a completion.
9. Return the complete CanvasDocument as next_document. It remains a proposal until the user applies and approves it.

## Authoring Rules

- References carry identity; initialization artifacts carry content. Do not duplicate large prompts inside nodes.
- Never use a graph edge to imply undeclared filesystem, tool, model, or network authority.
- Use repository-relative write scopes. Never include absolute paths, parent traversal, .git, or .formalprompt.
- Parallel agents must have disjoint write scopes unless a dependency orders them.
- Do not mark a guess as accepted merely to make validation pass.
- Do not add ornamental nodes. Every node must change readiness, produce an artifact, perform work, verify evidence, or make a decision.

## Verification

- The document matches schemas/agent-canvas-v1.schema.json.
- formalprompt validate reports no workflow errors before approval.
- Every referenced resource resolves and every harness capability is pinned.
- Required ports are connected with matching types.
- The graph is acyclic, fully reachable, and has complete terminal paths.
- The browser makes node provenance, authority, resources, and acceptance criteria inspectable.
