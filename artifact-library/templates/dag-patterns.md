# DAG pattern catalog — when to use which template

## Choosing the right shape

| Spec signal | DAG pattern | Nodes added | Review? |
|-------------|-------------|-------------|---------|
| Single feature, no unknowns | `workflow-minimal` | input→implement→test→gate→handoff | Optional gate |
| Two+ independent subsystems | `workflow-parallel` | Parallel agents + join(all) → integration | Gate before handoff |
| Load-bearing unknown before code | `workflow-research-implement` | research → artifact(knowledge) → implement | Gate |
| Must survive adversarial review | `workflow-full-lifecycle` | Full 10-node with independent review + checkpoint | Required |

## Join choice
- `all`: every branch must succeed (feature integration, test matrix).
- `any`: first success wins (fallback providers, speculative branches). Later successes ignored, not canceled; fails only after every input terminal.

## Scope heuristics
- Feature branch → `src/feature/**`
- Tests → `tests/**` (or co-located, but consistent)
- Research → `docs/research/**`
- Reports → `reports/**`
- Docs → `docs/**`
- Never `docs/**` and `src/**` from same parallel node — split them.

## Review repair
Always forward-only. `review.remediation.maximum_rounds: 3`, `repair_template: template.review-repair`, `exhaustion: block` (or request-user-decision when user must decide).

## Includes
Copy the chosen pattern doc into the workflow description and adapt node IDs, titles, and scopes to the project language.
