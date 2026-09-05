# Policy: Independent review gate

## Purpose
Guarantee that user approval is preceded by an independent, evidence-backed review when risk warrants it.

## Configuration
- Set `completion.require_independent_review: true` in the canvas when the spec requests review or risk warrants it (mismatched from existing flag only with evidence in rationale).
- Every `review` node must have `independent: true` and `independent_from: [<upstream agent node IDs>]`. A review that omits its upstream lineage is invalid.
- `remediation: {maximum_rounds, repair_template_resource, exhaustion: block|request-user-decision}` bounds repair as forward-only attempts, not cycles.

## Evidence required
- Review model, prompt resource, subject resources, and required evidence declared per node.
- The broker records a passing review bound to `revision` + `document_sha256`. Any later field, artifact, workflow, or proposal edit invalidates that pass.
- Compilation rejects a stale pass when the atomic document and state-file replacements diverge.

## When to include
Include this policy as an `execution-policy` artifact and as a `policy` resource referenced by `review` and `gate` nodes whenever independent review is required.

## Anti-pattern
Do not reuse the same agent for implementation and review with a different prompt — independence is about agent lineage, not prompt text.
