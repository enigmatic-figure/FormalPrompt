# Tuning the Muse Spark initialization composer

The Muse adapter has four deliberately separate inputs:

1. The packaged operating contract (`src/formalprompt/prompts/muse-facilitator.md`) defines protocol and safety invariants.
2. Optional environment guidance (`FORMALPROMPT_MUSE_GUIDANCE`) captures evidence-supported local policies.
3. The optional seed artifact library (`artifact-library/`) supplies composable task data.
4. The request JSON contains the current form state and operation.

Set `FORMALPROMPT_MUSE_PROMPT` to replace the operating contract during deliberate prompt experiments. Set `FORMALPROMPT_MUSE_GUIDANCE` to append a UTF-8 Markdown guidance file while keeping the base contract. Each file is limited to 262,144 bytes. The fresh read-only Muse job and its exact prompt remain preserved in the Muse runner logs.

The packaged `artifact-library/` is loaded by default (31 entries, ~85KB). Set `FORMALPROMPT_MUSE_LIBRARY` to a directory containing an external `formalprompt-artifact-catalog/v1`, or to `none` for an invocation that should receive no seeds. FormalPrompt confines catalog paths to the chosen directory and bounds total library content to 1,048,576 bytes.

## Library selection is catalog-driven, not vector-driven

With ~30 artifacts, Muse selects from the explicit `catalog.json` (`purpose` / `use_when` / `avoid_when`) and the in-prompt contents. This is deliberate: selection is auditable, reproducible, and fits the declarative-contract philosophy. A LanceDB/vector step would hide authority behind embedding similarity, make debugging harder, and save negligible tokens at this scale (full catalog ≈ 18–22k tokens).

Vector search would only merit consideration if the library grew past ~100 artifacts and retrieval precision mattered more than auditability. Even then, the catalog would remain the source of truth and the index would be a derived cache with explicit fallback to full-catalog evaluation for small catalogs.

The catalog already carries the signal a future indexer would need: stable IDs, `purpose`, `use_when`/`avoid_when`, and `kind`. If you later experiment with retrieval, embed those fields plus artifact headers and keep the 1MB bound as the budget for the retrieved subset.

## Recommended history-informed tuning loop

1. Give Muse selected historical session windows plus the graph, initialized artifacts, Git diff, and model/resource assignment that produced each behavior.
2. Ask her to describe candidate interpretation or artifact-selection policies and the evidence against each one. Codex behavior is evidence, not ground truth.
3. Separate environment facts, user preferences, model-specific accommodations, and one-off local repairs. Only the first two are plausible default guidance without further evidence.
4. Test candidate guidance against `examples/muse-composer-evals.json` and matched historical cases. Look for fewer unnecessary questions and smaller graphs without lost constraints or invented intent.
5. Promote a policy into durable guidance only after checking counterexamples. Keep the supporting session references outside the runtime prompt; the policy itself should be compact.
6. Dogfood the resulting canvas with a human visual review. Approval affirms the complete graph; node provenance remains a cue for where scrutiny is useful.

The seed library is intentionally composable. Muse may select, adapt, omit, or propose replacements for its entries. She should materialize selected content as canvas initialization artifacts so the compiled project is self-contained.

## First manual dogfood pass

```text
uv run formalprompt template workflow-project dogfood-canvas.json
set FORMALPROMPT_MUSE_REPO=E:\path\to\target-project
set FORMALPROMPT_MUSE_GUIDANCE=E:\path\to\muse-guidance.md
set FORMALPROMPT_MUSE_LIBRARY=E:\path\to\artifact-library
uv run formalprompt open dogfood-canvas.json --assistant-command formalprompt-muse-assistant --assistant-timeout 630
```

For PowerShell:
```powershell
$env:FORMALPROMPT_MUSE_REPO="E:\path\to\target-project"
$env:FORMALPROMPT_MUSE_GUIDANCE="E:\path\to\muse-guidance.md"
$env:FORMALPROMPT_MUSE_LIBRARY="E:\path\to\artifact-library"
uv run formalprompt open dogfood-canvas.json --assistant-command formalprompt-muse-assistant --assistant-timeout 630
```

Start with one real but recoverable project. Inspect whether the forms ask only consequential questions, whether every graph resource resolves to a useful artifact, whether scopes and review checkpoints match intent, and whether the compiled handoff lets Codex begin without reconstructing the initialization discussion.

## Companion artifacts

- `artifact-library/knowledge/repo-conventions.md` — give `input` nodes the actual repo layout so agents don''t guess.
- `artifact-library/knowledge/product-brief.md` — one-page approved-intent context for scoped agents.
- `artifact-library/templates/dag-*.md` — copy the right DAG shape instead of inventing one.
- `artifact-library/policies/*.md` — bind isolation and review invariants as explicit policy resources.
- `examples/muse-environment-guidance.example.md` — scaffold for local guidance; keep policies compact and evidence-backed.
