# FormalPrompt seed artifact library — composer toolbox

This directory is Muse Spark''s **selection library**, not a bundle every project receives. Muse selects the smallest applicable set, adapts each file to the project''s language, and copies the result into the canvas as typed initialization artifacts (`initialization.artifacts`). Compiled workflow nodes reference those materialized artifacts by ID — never this external directory.

## What''s inside (31 entries)

- **Agents (4)**: incident-responder, builder, verifier, researcher — each defines authority, read-before-write, scope discipline, and the single-intervention rule.
- **Prompts (8)**: implementation, verification, independent-review, handoff, research, report, design, api-contract, planning — each prompt is a role-scoped instruction that fits one node kind, not a general assistant.
- **Skills (4)**: tdd, api-design, documentation, browser-canvas — reusable methods that an agent node can declare in `skill_resources`.
- **Policies (4)**: intervention-bookmark, write-scope-isolation, review-gate, deviation — execution policies that make intent-preserving behavior inspectable.
- **Templates (6)**: review-repair, dag-minimal, dag-parallel, dag-research-implement, dag-full-lifecycle, dag-patterns — DAG shapes, not implementation.
- **Knowledge (2)**: repo-conventions, product-brief — concise context that `input` or `agent` nodes consume as `context_resources`.
- **Report templates (2)**: verification, handoff-manifest.

`catalog.json` lists `purpose`, `use_when`, and `avoid_when` for each — selection guidance, not a fixed graph. Muse must prefer references over duplication, pin capabilities, and keep the graph acyclic.

## Bounds

- Each artifact ≤262,144 bytes (Muse runner limit).
- Total catalog + contents ≤1,048,576 bytes (currently ~85KB, well within).
- `harness-capability` resources (e.g., `terminal@codex-runtime/v1`, `git-checkpoint@codex-runtime/v1`) are *not* files here; they are pinned capabilities resolved at execution preflight.

## How to use this library

1. Composition time: Muse reads `catalog.json` + contents, selects a minimal set, adapts text to the spec, and materializes as `initialization.artifacts`. The workflow''s `resources` then bind to those IDs.
2. Execution time: Codex reads `EXECUTION_CONTRACT.md` + `workflow.json` + the materialized files under `.formalprompt/runs/<id>/artifacts/initialization/`. It never sees this directory.

## LanceDB / vector search?

Not needed at this scale. With ~30 items, an explicit catalog with deterministic selection guidance is more auditable and reproducible than embedding similarity. The catalog is deliberately structured with `purpose`/`use_when`/`avoid_when` and could be indexed later if it ever exceeds ~100 items, but for v0.1 the token cost of sending the full catalog (~20k tokens) is trivial and the debuggability wins.

## Tuning guidance

Changes here should be evaluated across several initialization cases (see `examples/muse-composer-evals.json`). A local project intervention is evidence for later high-context audit — not automatic authority to mutate library files. See `docs/muse-tuning.md`.
