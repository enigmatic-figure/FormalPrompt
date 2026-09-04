# Tuning the Muse initialization composer

The Muse adapter has four deliberately separate inputs:

1. The packaged operating contract defines protocol and safety invariants.
2. Optional environment guidance captures evidence-supported local policies.
3. The optional seed artifact library supplies composable task data.
4. The request JSON contains the current form state and operation.

Set `FORMALPROMPT_MUSE_PROMPT` to replace the operating contract during deliberate prompt
experiments. Set `FORMALPROMPT_MUSE_GUIDANCE` to append a UTF-8 Markdown guidance file while keeping
the base contract. Each file is limited to 262,144 bytes. The fresh read-only Muse job and its exact
prompt remain preserved in the Muse runner logs.

The packaged `artifact-library/` is loaded by default. Set `FORMALPROMPT_MUSE_LIBRARY` to a directory
containing an external `formalprompt-artifact-catalog/v1`, or to `none` for an invocation that should
receive no seeds. FormalPrompt confines catalog paths to the chosen directory and bounds total
library content to 1,048,576 bytes.

The recommended history-informed tuning loop is:

1. Give Muse selected historical session windows plus the graph, initialized artifacts, Git diff,
   and model/resource assignment that produced each behavior.
2. Ask her to describe candidate interpretation or artifact-selection policies and the evidence
   against each one. Codex behavior is evidence, not ground truth.
3. Separate environment facts, user preferences, model-specific accommodations, and one-off local
   repairs. Only the first two are plausible default guidance without further evidence.
4. Test candidate guidance against `examples/muse-composer-evals.json` and matched historical cases.
   Look for fewer unnecessary questions and smaller graphs without lost constraints or invented
   intent.
5. Promote a policy into durable guidance only after checking counterexamples. Keep the supporting
   session references outside the runtime prompt; the policy itself should be compact.
6. Dogfood the resulting canvas with a human visual review. Approval affirms the complete graph;
   node provenance remains a cue for where scrutiny is useful.

The seed library in `artifact-library/` is intentionally composable. Muse may select, adapt, omit,
or propose replacements for its entries. She should materialize selected content as canvas
initialization artifacts so the compiled project is self-contained.

## First manual dogfood pass

```text
uv run formalprompt template workflow-project dogfood-canvas.json
set FORMALPROMPT_MUSE_REPO=E:\path\to\target-project
set FORMALPROMPT_MUSE_GUIDANCE=E:\path\to\muse-guidance.md
set FORMALPROMPT_MUSE_LIBRARY=E:\path\to\artifact-library
uv run formalprompt open dogfood-canvas.json --assistant-command formalprompt-muse-assistant
```

For PowerShell, assign those values through `$env:` instead of `set`. Start with one real but
recoverable project. Inspect whether the forms ask only consequential questions, whether every graph
resource resolves to a useful artifact, whether scopes and review checkpoints match intent, and
whether the compiled handoff lets Codex begin without reconstructing the initialization discussion.
