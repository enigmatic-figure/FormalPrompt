# Workflow template: Research → Implement → Verify

## Sequence
`input` → `operation: research` → `artifact: knowledge` → `agent: implement` → `operation: test` → `handoff`

- **research**: prompt.research + agent.researcher, write_scope=["docs/research/**"], produces `knowledge.repo-conventions` or a topic synthesis.
- **artifact: knowledge** (read): binds the produced research artifact for downstream nodes.
- **implement**: prompt.implementation + agent.codex-builder, context_resources=[knowledge.*], skill_resources=[skill.tdd], write_scope=["src/**","tests/**"], consumes research as `context` edge.
- **test**: prompt.verification, write_scope=["tests/**", "reports/**"], consumes `evidence` from implement.

## Why this ordering
Research output becomes an explicit resource; implementation does not guess at unknowns already resolved. The DAG preserves acyclicity while making the dependency visible.

## When to use
The spec has load-bearing unknowns (API shape, repo conventions, feasibility) that should be resolved as a durable artifact before implementation authority is granted.

Kind: `workflow-template`.
