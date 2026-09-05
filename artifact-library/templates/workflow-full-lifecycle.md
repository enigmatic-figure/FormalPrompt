# Workflow template: Full lifecycle with independent review

## Canonical graph (10 nodes)
`intent` → `operation: research` → `agent: implement` → `operation: test` → `review: independent` → `gate: user-approval` → `operation: report` → `checkpoint: git` → `handoff`

Branches optional:
- `research` and `plan` can run in parallel and join(all) before `implement`.
- Multiple `agent: implement` nodes can run in parallel on disjoint scopes with an `all` join before integration test.

## Node declarations (abbreviated)
- `input:input` resource_ids=[knowledge.product-brief, prompt.implementation]
- `agent:implement` model=codex, prompt_resource=prompt.implementation, agent_definition=agent.codex-builder, context_resources=[knowledge.*], skill_resources=[skill.tdd], tool_resources=[tool.terminal], write_scope=["src/**","tests/**","docs/**"], acceptance_criteria from spec
- `operation:test` operation=test, instruction_resource=prompt.verification, write_scope=["tests/**","reports/**"]
- `review:independent` model=codex, prompt_resource=prompt.independent-review, independent=true, independent_from=[implement], remediation={maximum_rounds:3, repair_template_resource=template.review-repair, exhaustion:block}
- `gate:approval` gate=user-approval, criteria=["Independent review passed or user explicitly accepted risks"]
- `operation:report` operation=report, instruction_resource=prompt.report, write_scope=["reports/**"]
- `operation:checkpoint` operation=checkpoint, instruction_resource=prompt.handoff, resources=[tool.git-checkpoint], no filesystem scope (capability)
- `operation:handoff` operation=handoff, instruction_resource=prompt.handoff, write_scope=["docs/**","reports/**"]

## Resources (pinned)
prompt.implementation, prompt.verification, prompt.independent-review, prompt.handoff, agent.codex-builder, agent.verifier, template.review-repair, policy.intervention-bookmark, tool.terminal@codex-runtime/v1, tool.git-checkpoint@codex-runtime/v1

## Policy
entry_nodes=[intent], completion_nodes=[handoff], maximum_parallel_nodes=3, failure=halt, deviation=allow-narrow

## When to use
Any project that requires an evidence-backed handoff and must survive independent review.

Kind: `workflow-template`.
