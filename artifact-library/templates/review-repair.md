# Review repair attempt — bounded, finding-specific

## Mandate
Repair every **confirmed** finding against the immutable review checkpoint. Preserve approved behavior; do not redefine completion.

## Method
1. Re-evaluate every finding against the current repository before editing. Classify: confirmed blocker, unreproducible, risk, or preference.
2. For each confirmed blocker, edit only inside its implicated scope. Preserve intended behavior outside that scope. Cite the file and line you changed.
3. Run focused regression checks: the single test or reproduction that proves the finding, then the broader suite relevant to the changed area. Capture command and tail.
4. If the workflow declares an independent review gate, publish an immutable remediation checkpoint (commit + optional tag) and request a narrow closure review from the same reviewer. Follow `remediation.exhaustion` when `maximum_rounds` is reached.
5. Stop when the reviewer reclassifies remaining findings as non-blockers or the exhaustion path requests a user decision.

Do not collapse repair attempts into one overwritten status. Each attempt is a new forward-only record in Git and the session log.

Artifact kind: `workflow-template`. Referenced by `review` nodes as `repair_template_resource`.
