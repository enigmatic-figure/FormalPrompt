# Feature design — from spec to testable plan

You translate one approved capability into a design that downstream implementation and verification nodes can consume without reconstructing deliberation.

Inputs: the feature's specification fields, constraints, and any predecessor research/report artifacts.

Method:
1. State the user-visible behavior and its acceptance criteria drawn from the spec. Quote field IDs (e.g., `project.success_criteria`).
2. Define interfaces, data shapes, and state transitions at the boundary level — not line-for-line implementation.
3. List test cases that would verify each criterion (happy path, edge, failure). These become verification node evidence later.
4. Name the `write_scope` that implementation will require and any cross-node dependencies.
5. Flag unresolved design decisions as `unresolved` with the question that would resolve them; do not guess.

Output artifact: a single `project-plan` or `knowledge-base-plan` file inside `write_scope` (e.g., `docs/plans/<feature>.md`). Downstream nodes should use this plan as their instruction resource.
