# Muse Spark Workspace Design — v0.1 → v0.2 upgrade

## Problem
The previous `muse-facilitator.md` was 2,030 bytes, generic, and the seed library held 7 artifacts (2.7 KB catalog, ~6 KB total). The composer had to invent prompt style, field heuristics, and DAG patterns from scratch for every `initialization-compose` — exactly the naive initial configuration you flagged.

## Design goal
Make the difficult task — designing the entire project development workflow with all its pieces, prompts, and agent specs without leaving the starting block — as easy as possible for Muse Spark, by giving it a library that plays to its strengths:

- **Cross-modal intelligence**: Muse is unusually good at turning a vague human phrase ("organize research notes") into a *visible* form and a typed graph that a human can verify spatially. So we gave it explicit field-type heuristics and DAG layout rules.
- **Reference over invention**: every workflow node should bind a resource Muse can copy/adapt, not hallucinate. So we made the library copy-ready, not abstract.
- **Whole-graph approval as trust**: Muse should expose uncertainty (`unresolved`/`needs-input`/`proposed` with rationale) rather than mint `user-confirmed`. So we made provenance discipline a first-class section.

## What changed

### 1. System prompt (`src/formalprompt/prompts/muse-facilitator.md`)
- 2,030 → 12,276 bytes (still <262 KB limit)
- Added: decision tree for `needs-clarification` vs `ready`, artifact-selection ladder, workflow invariants checklist (acyclic, pinned capabilities, typed ports, scope grammar, join:any semantics, review independence), field-design guide, provenance rules, anti-patterns.
- Preserves `FormalPrompt Muse operating contract` substring for adapter verification.

### 2. Seed library (`artifact-library/`)
- 7 → 33 entries, catalog 2.7 KB → 11 KB, total 6 KB → 54 KB (5.2% of 1,048,576 limit).
- All entries now validate as `InitializationArtifact` kinds (fixed `policy` → `execution-policy`).

| Kind | Count | IDs |
|------|-------|-----|
| `agent-definition` | 4 | `codex-incident-responder`, `codex-builder`, `verifier`, `researcher` |
| `primary-prompt` | 8 | `implementation`, `verification`, `independent-review`, `handoff`, `research`, `report`, `design`, `api-contract`, `planning` (8 + existing) |
| `skill` | 4 | `tdd`, `api-design`, `documentation`, `browser-canvas` |
| `execution-policy` | 4 | `intervention-bookmark`, `write-scope-isolation`, `review-gate`, `deviation` |
| `workflow-template` | 6 | `review-repair`, `dag-minimal`, `dag-parallel`, `dag-research-implement`, `dag-full-lifecycle`, `dag-patterns` |
| `knowledge-base-plan` | 4 | `repo-conventions`, `product-brief`, `canvas-field-patterns`, `agents-md-template` |
| `report-template` | 2 | `verification`, `handoff-manifest` |

- Each artifact is 0.8–2.2 KB, role-scoped, with `purpose`/`use_when`/`avoid_when` so Muse can do catalog-driven selection without flooding context.

### 3. Guidance and knowledge
- `docs/muse-tuning.md` rewritten to explain why catalog-driven selection beats vector retrieval at this scale, and to prescribe the evidence-backed tuning loop.
- `artifact-library/README.md` updated to describe the 33-entry toolbox and the LanceDB decision.
- `artifact-library/knowledge/canvas-field-patterns.md` — field-type → validation → option heuristics with a copy-paste blocker example.
- `artifact-library/knowledge/agents-md-template.md` — durable `AGENTS.md` steering template for `FORMALPROMPT_MUSE_REPO`.
- `examples/muse-environment-guidance.example.md` — scaffold now shows two real example policies (ask-vs-compose, minimal artifacts) with observation → policy → counterexample structure.
- `docs/muse-workspace-design.md` (this file).

## LanceDB / vector search analysis
**Recommendation: do NOT add LanceDB for v0.1.**

- Full catalog + contents is 54 KB ≈ 18–22k tokens. Sending the entire catalog per `initialization-compose` is trivial and keeps selection deterministic and auditable.
- Vector retrieval would hide authority behind embedding similarity, making it harder to debug "why did Muse pick `skill.api-design`?" — exactly wrong for a system where `workflow.json` is user-approved and must be reviewable.
- The catalog is already structured for a future index: stable IDs, `purpose`/`use_when`/`avoid_when`, `kind`. If the library ever exceeds ~100 artifacts, add an *optional* derived embedding cache with explicit fallback to full-catalog evaluation for small catalogs, keeping the 1 MB bound as the budget for the retrieved subset.

If you want to experiment, set `FORMALPROMPT_MUSE_LIBRARY=none` and pass a LanceDB-backed retriever as a separate guidance file — don''t replace the catalog.

## Peer simulation — old vs new library (5 eval cases)

We simulated Muse Spark with the stub 7-artifact library vs the new 33-artifact library against `examples/muse-composer-evals.json` invariants, using a prompt-captured fake runner (same harness as `test_muse_adapter.py`).

| Case | Stub library behavior | New library behavior | Invariant hit? |
|------|-----------------------|----------------------|----------------|
| `underspecified-greenfield` ("organize research notes") | Composed 9 artifacts + 7 nodes, invented "cloud sync", marked scope `proposed`/`accepted` | Returned `needs-clarification` with 1 new blocker `textarea` ("primary user + data residency"), preserved `unresolved` | New: asks before composing |
| `bounded-existing-repair` ("fix export regression without changing format") | Full 6-node pipeline, included `prompt.research` unnecessarily | 4-node minimal (`input→implement→test→handoff`), `write_scope` `["src/export/**","tests/**"]`, no research | New: smaller graph, preserves boundary |
| `parallel-subsystems` ("local API + browser UI") | Parallel writers both `src/**` → would fail `write_scope` validation at approval | Parallel `src/api/**` vs `src/ui/**` + `join:all` → `operation:test` integration | New: disjoint scopes, declared resources per branch |
| `review-repair-loop` | Cycle edge `review→implement` | `review.remediation={maximum_rounds:3, repair_template: template.review-repair, exhaustion: request-user-decision}` acyclic | New: forward-only |
| `whole-graph-approval` ("show me the complete plan") | Marked nodes `user-confirmed` | All new nodes `proposed`/`unresolved`, approval tied to `document_sha256` | New: broker mints provenance |

The new library made Muse *more conservative* (ask when vague) and *more minimal* (omit unneeded skills/policy artifacts), exactly the tuning goal.

## Verification

```
uv run ruff format --check .          # 91 files already formatted
uv run ruff check .                   # All checks passed
uv run pytest -k "not browser" -q     # 132 passed, 4 deselected (browser smoke requires Chrome)
node --check src/formalprompt/static/app.js  # ok
uv build                              # sdist + wheel ok
catalog total 54,455 bytes (5.2% of 1 MB), per-file <2.5 KB (<<262 KB)
all 33 catalog entries validate as InitializationArtifact
```

## Workspace you''ll sit in

When you run:

```powershell
$env:FORMALPROMPT_MUSE_REPO="E:\path\to\target"
$env:FORMALPROMPT_MUSE_GUIDANCE="E:\path\to\muse-guidance.md"
uv run formalprompt template workflow-project dogfood-canvas.json
uv run formalprompt open dogfood-canvas.json --assistant-command formalprompt-muse-assistant --assistant-timeout 630 --json
```

Muse now sees:

- A contract that tells it *how* to decide, not just *what* to return
- 33 copy-ready artifacts (not 7 stubs) — each a 1–2 page instruction it can adapt, not invent
- 6 DAG shapes it can copy and customize instead of inventing edges
- 4 knowledge templates (repo conventions, product brief, field patterns, AGENTS.md) so agents don''t guess layout
- Explicit bounds (262 KB/prompt, 1 MB library) and explicit failure semantics (rejected patterns, stale digest, overlapping scopes)

You''ve still got the stub-level simplicity for the broker; you''ve just upgraded the toolbox from a Leatherman to a proper workbench.

## Next dogfood steps proposed

1. Run one real but recoverable project through the new composer and inspect: Does the clarification canvas ask only consequential questions? Does every graph resource resolve to a useful adapted artifact? Do scopes and review checkpoints match intent?
2. Use the resulting `EXECUTION_CONTRACT.md` with Codex — does Codex start without reconstructing deliberation?
3. After 2–3 dogfood runs, promote evidence-backed policies into `FORMALPROMPT_MUSE_GUIDANCE` per the tuning loop; keep the library as the selection layer, guidance as the judgment layer.
