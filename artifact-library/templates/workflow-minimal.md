# Workflow template: Minimal linear lifecycle

## Structure (4–5 nodes + edges)
`input` → `agent: implement` → `operation: test` → `gate: verification` → `handoff`

- **input**: `resource_ids: [prompt.implementation]` (approved intent)
- **agent: implement**: model=codex, prompt_resource=prompt.implementation, agent_definition=agent.codex-incident-responder, write_scope=["src/**","tests/**"], acceptance_criteria from spec, timeout 3600
- **operation: test**: operation=test, instruction_resource=prompt.verification, write_scope=["tests/**"], acceptance_criteria: tests pass
- **gate: verification**: gate=verification, criteria: unit+integration pass
- **handoff**: operation=handoff, instruction_resource=prompt.handoff, write_scope=["docs/**","reports/**"]

## Resources
prompt.implementation, agent.codex-incident-responder, prompt.verification, prompt.handoff, tool.terminal (harness-capability terminal@codex-runtime/v1)

## When to use
Greenfield or single-feature projects that need no research, no parallel branches, and no independent review.

## Ports
All edges are `control` except artifact edge from implement→test if the test consumes produced code (still control for sequencing).

Keep position left→right by level. Set `entry_nodes: [input]`, `completion_nodes: [handoff]`, `maximum_parallel_nodes:1`.

Kind: `workflow-template`.
