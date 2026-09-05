# Knowledge: Canvas field patterns — good forms that converge

## When to add a field
A field should exist only if its answer changes the artifact set, the write scope, or an acceptance criterion. If the answer would not change the graph, it is not consequential.

## Type choice
- `text` — short identifier, name, version, single path.
- `textarea` — objective, success criteria, narrative, exclusions. Use `min_length` validation (10–20) for blockers.
- `select` — 2–5 mutually exclusive choices with distinct `implications` (e.g., `distribution: source|package|binary`).
- `multiselect` — independent capabilities that compose (e.g., `platforms: windows|macos|linux`).
- `checkbox` — binary invariant that must be explicit (e.g., `allow_remote: false`).
- `number` — bounded numeric with `minimum`/`maximum` (timeouts, budgets, thresholds).

## Validation
- `min_length` for required narrative blockers (10).
- `pattern` only as server-enforced RE2 (512 chars, linear). Never for user enumeration — use `select`.
- `required: true` + `importance: blocker` + `provenance: unresolved` + `review_status: needs-input` — the combination that blocks approval.

## Options
Each `select`/`multiselect` option needs `value` (machine), `label` (human), and `implications` (one sentence of consequence). Good implications change a builder''s decision. Bad: "Uses X". Good: "Requires platform build and larger release artifacts."

## Provenance discipline (for generated canvases)
- Preserve explicit/user-confirmed values verbatim.
- Mark your new fields `unresolved`/`needs-input`/`blocker` when they require a user decision.
- Mark defensible defaults `proposed`/`unreviewed` with brief `rationale` (one sentence).
- Mark synthesis from repo evidence `inferred` with evidence pointer.

## Assistance
Enable `assistance: {enabled:true, prompt:"Compares X tradeoffs without inventing scope."}` only when the field''s implications are genuinely ambiguous. Don''t enable everywhere.

## Example blocker (good)
```json
{
  "id": "project.objective",
  "label": "Primary objective",
  "type": "textarea",
  "value": null,
  "description": "State the concrete result the project should produce.",
  "placeholder": "What should exist or work when this project is complete?",
  "required": true,
  "importance": "blocker",
  "provenance": "unresolved",
  "review_status": "needs-input",
  "validation": {"min_length": 10},
  "assistance": {"enabled": true, "prompt": "Offer precise, outcome-oriented alternatives without inventing scope."}
}
```

This knowledge binds as `knowledge-base-plan` and is referenced by clarification canvases to keep form language consistent.
