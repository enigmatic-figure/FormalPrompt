# Workflow template: Parallel branches with join

## Pattern
```
intent
  ├─ agent: implement feature A (scope: src/feature-a/**)
  ├─ agent: implement feature B (scope: src/feature-b/**)
  └─ operation: research C (scope: docs/research/**)
           │
      join: all  ─→  operation: test (integration)  ─→  gate: verification  ─→  handoff
```

## Key invariants
- Parallel writers have disjoint scopes → validated by write-scope-isolation policy.
- Each branch depends only on `intent` (no cross-branch edges) and converges on `join:all`. No node is unreachable; every node reaches handoff.
- `join:all` ports: branch-a, branch-b, branch-c (control, required, multiple:false). Ready only after every branch succeeds.

## Resources per branch
- Feature A: prompt.implementation + agent.codex-builder + skill.tdd
- Feature B: same with feature-specific context
- Research C: prompt.research + agent.researcher

## When to use
Spec decomposes into independent subsystems with non-overlapping write scopes and a shared integration check.

## Ports
Branch edges = `control`. Integration test consumes `evidence` edges from each branch if verification proof is needed.

If any branch fails, join fails; remediation follows the review node that follows the join.

Kind: `workflow-template`.
