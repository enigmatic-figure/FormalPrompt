# Session reflection — FormalPrompt vs two real Codex sessions (2026-08)

> Throwaway folder `sessionTesting/` contains two rollout JSONLs actually performed on this machine.
> This doc reflects on how the current FormalPrompt system (v0.2 workspace: 12.3KB prompt + 33-entry library) would have performed under those *real* prompts, outcomes, and implementation paths — what it would have done differently, what Codex got right that FormalPrompt still doesn''t, and what we should change.
> Take as long as needed — this is not peer-review, it''s a personal inquiry to decide direction, just like you said for the CoT work.

---

## 1. Rollout `01a004d9` — CoT continuous-embedding experiment

### 1.1 What the prompts actually were (19 prompts, non-env)

| # | Len | Core intent |
|---|-----|-------------|
| 1 | 165 | "In the mood to help me design and implement a Colab experiment to make AI C-o-T systems better?" — ultra-under-specified opener |
| 2 | 8,629 | **The real spec:** another agent''s `Cot_Experiment.md` is 85–90% right; 5 precise fixes: (1) indexing `x_t→h_t→ℓ_{t+1}→e_{1,t+1}→E_{t+1}`, (2) exact lexical control ≠ native DeepSeek, add native greedy baseline + measure `T`, (3) missing crowded-field input `N_eff=1/Σp_i²`, (4) norm geometry `\|h_t\|` vs `\|e_1\|` before mixing + `tilde h` variant, (5) paired drift: total-effect vs isolation + win-rate `W` and gain `G` diagnostics. Plus endpoint ablations (`e1/e2`, `e1/h`, static mixture) and KV-cache requirement. |
| 3 | 310 | "You may yeet to a private repo if convenient" — sandcastle permission |
| 4 | 2,283 | **Framing:** this is *personal, informal, not peer-review*; just "move the needle" before deciding what goes into the larger, above-reproach demonstration. Tokens are discretization; let self-talk be continuous; later train second half with independent model. Run on Colab T4 via `colab-cli` in WSL. |
| 5 | 54 | "you can begin a dynamic-controller search" — go signal |
| 6 | 332 | Archive to `C:/`, add `e3` branch to polytope |
| 7–12 | 550–472 | Hardware negotiation: local 8GB + 4050 vs T4 vs v5e-1 TPU (16GB HBM) vs Kaggle P100/T4x2/v5e-8; Kaggle CLI async batch noted; legacy `kaggle.json` provided |
| 13 | 4,767 | Kaggle T4x2 log readout (hardware 2×T4, torch 2.10, splits c8/s24/v24/h96, running state) |
| 14 | 317 | Quick-fix thesis: flip switches, not weights |
| 15 | 847 | Larger project is *native-representation reasoning* with soft-snapping; this ad-hoc C-o-T is optional but worth the 14% basin argument |
| 16 | 620 | Gen3 done, gen1 still best: `e1_e2_h 2.10 val` vs `e1_e2_e3_h 2.21` |
| 17 | 30 | "our kaggle run has wrapped up" |
| 18 | 6,705 | **Post-run human synthesis:** *much narrower and much larger* next: Stage 1 static-α sweep `E=(1-α)e1+α tilde h, α∈{0,.025,.05,.075,.10,.125,.15,.20}`, response curve shape > best point, paired ΔL, 192 selection / 384 test, then Stage 2 tiny adaptive `α_t=α0+δ_t` with 3–4 inputs (`ℓ1-ℓ2`, `p1`, `N_eff`, `cos(h,e1)`) |
| 19 | 35 | "last kaggle run has wrapped up" |

Tool summary: **384 `exec` + 203 `wait`** — the implementation was 800 shell steps, not 6 workflow nodes.

Final outcome (quoted from assistant final):
> Static `0.9e1+0.1 tilde h` — holdout 2.2345 vs lexical 2.4007 — **-6.92% NLL, 15.3% perplexity**, `W=64.6%` (62/96, Wilson CI [54.6,73.4]), `G=-0.166`, median -0.094, not jackpot-driven. Dynamic `e1/e2/h` +1.25% (ns), `e1/e2/e3/h` +0.49%. 
> Codex then encoded the staged A/B/C program (response-curve T4x2, 52b12d3, allowlist 18 files, 15 tests, 12.5h, 495 reserved).

### 1.2 How FormalPrompt would have performed

**Where it would have helped (and our new library closes the gap):**

* **Externalizing the 5 fixes.** Those fixes are exactly the `CanvasField` discipline we now teach in `knowledge/canvas-field-patterns.md`: `blocker` + `required` + `unresolved` + `needs-input`. In the real run Codex patched `Cot_Experiment.md` inline via `apply_patch` — auditable in Git but not in a form. FormalPrompt would have materialized them as fields/artifacts:
  * `field.experiment.indexing` — `textarea` with `E_{t+1}=f(h_t,e_{1,t+1},…)` + KV-cache acceptance criterion
  * `field.baseline.lexical_control` — `select` {`exact-64`, `native-unconstrained`, `manual-fixed-budget`} with implications
  * `field.controller.crowded_field` — `N_eff` / entropy as `number` + `checkbox` "include in φ_t"
  * `field.geometry.norm_match` — `select` {`raw h`, `tilde h`} + measurement step
  * `field.evaluation.paired_drift` — two paired tests with `W>0.5` ∧ `G<0` CIs, cheap CMA objective + periodic audit
  * Our new `prompt.research` + `prompt.design` + `report.verification` template already expects `G`, `W`, bootstrap CI, exact-match, trimmed means — so the current system *would now* produce that report shape. The old 7-entry stub would have missed `N_eff`, norm, and paired `W`.
* **Hardware choice as a field.** The T4 vs v5e-1 vs Kaggle v5e-8 negotiation was handled in chat. FormalPrompt would have made it a `multiselect` with `implications`: `T4: 2×15GB, 74 TFLOPS, immediate queue; v5e-1: 1×16GB+197 TFLOPS but JAX; Kaggle: 30h/week, async batch, 20-min TPU queue`. That would have been *better* than chat — it preserves the tradeoff and lets the user pick via the browser, not via free-form.
* **DAG staged program.** After Stage A failed for dynamic, Codex manually proposed the narrow-then-tiny-adaptive sequence in chat. FormalPrompt''s `template.dag-research-implement` and our new `policy.review-gate` + `gate: user-approval` would have encoded that as `Stage 1: static α sweep (8 paired values, 192+384, all policies on every problem, 20% falsification) → gate: curve minimum stable → Stage 2: δ_t = wᵀφ_t+b with α_t∈[0,.20]`. The DAG makes the *non-leakage* explicit (248 prior questions excluded via SHA-256 signature, 495 reserved). Codex did this correctly via `local_run.json` signature; our `knowledge.repo-conventions.md` would have reminded it, but FormalPrompt''s compilation would have pinned the dataset revisions as `knowledge` resources — also correct, just formalized.

**Where it would have struggled or been too heavy:**

* **The "don''t go overboard" instruction.** Prompt 4 explicitly says "we aren''t seeking peer review, just move the needle" and "tokens are numbers, let self-talk be native language." FormalPrompt''s default is *maximally formal* — every blocker blocks approval. For a personal inquiry, the user *wanted* low friction. Our current `muse-facilitator.md` says "if objective contains ≤2 concrete nouns that bound scope and success criteria are unverifiable, return needs-clarification." Under that rule, Prompt 1 ("make C-o-T better") and even Prompt 4 would have triggered a clarification canvas, delaying the search the user explicitly wanted to start ("you can begin a dynamic-controller search"). Codex correctly *did not* block — it updated the doc and ran CMA-ES. FormalPrompt would have added one extra round-trip that the user didn''t want for this run. Lesson: we need a *lightweight/inquiry mode* where the canvas can be approved with an explicit `informal: true` flag that relaxes `unresolved-blocker` from error to warning. Our new library doesn''t have that — all `unresolved` blockers still block.
* **Adaptive narrowing based on interim evidence.** The workflow DAG is approved *before* execution and assumed to be the complete intent. The decision to narrow from 4-way polytope to 1-D α edge was made *after* seeing that dynamic 1.25% was ns and static -6.9% was real. That''s not a `review.remediation` repair of a failed check — it''s a human scientific judgment to change the *question*. Our DAG has no first-class "evidence-gated stage decision" node type — only `gate: user-approval | verification | policy`. We would have forced this through an `intervention` marker + `gate: user-approval` + a *new* canvas, which is correct per the sparse-intervention philosophy (Git holds what changed, session log holds what happened, marker joins them; don''t rewrite graph to look planned), but it would feel bureaucratic for a 2-hour inquiry. Codex''s approach — running the full polytope, then re-planning the next Kaggle run manually — was more fluid.
* **Kaggle batch transport.** The current library has no `kaggle-batch` or `colab-cli` harness capability templates, no allowlist pattern (`18 files, no credentials`), no dual-T4 sharding pattern. Codex invented those correctly (pinned model `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B@ad9f0ae`, split sizes, dual-T4 problem sharding). FormalPrompt would have blocked compilation until a `harness-capability` was pinned — good for auditability, but the library didn''t offer the right capability to pin. We need to add it.

**What Codex got right that our system still can''t:**

* Turning 8,629 chars of dense math into *running T4x2 code* without ever asking "which dataset?" — it inspected `datasets` via `rg`, discovered GSM8K (7,473 train / 1,319 test in log), measured native reasoning lengths, and inferred the right search harness. FormalPrompt would have demanded those as explicit fields; Codex''s "inspect repo then decide" is lighter for research spikes.
* Handling the huge async Kaggle log (500-line batch log) via bounded output (drain with limit, timeout 75s, fragment not query) — FormalPrompt''s `assistant.py` already does this (bounded streams, group kill), so we match there.
* Diagnosing the tail-risk mode: 60% wins but worse mean → exponential jackpot vs reliable drift. That surfaced as `report.verification` criteria (`mean ΔL`, median, trimmed mean, Wilson CI, McNemar) — our new template now requires those, but the old stub didn''t.


### 1.3 Verdict for CoT

The experiment *did* find the underlying claim — discrete tokens are not the best steering signal even without training — just not via the dynamic controller. FormalPrompt would have made the *static* positive result more credible sooner (paired CIs, response curve, exact problem-exclusion integrity), but would have added friction to the initial personal-inquiry phase. The next staged A/B/C program that Codex now launches is exactly where FormalPrompt''s DAG shines: two T4s evaluating 8 α on every problem, paired, with falsification at 0.20 — that''s a `dag-parallel` join (`all`) with `policy.write-scope-isolation` and pinned revisions.

---

## 2. Rollout `01a01ea7` — Codex CLI tools: Muse sub-agent + ChatGPT automated review

### 2.1 What the prompts were (21 prompts)

| # | Core | Pattern |
|---|------|---------|
| 1 | 6,530 | **Long-horizon harness brief:** 2 upgrades — (a) Muse long-context sub-agent via `MUSE_API_KEY` + `model.toml` + python example, cost ($0.83 for 140M cached) + system where Codex authors Muse''s own skills in `.codex`; (b) automated adversarial review via browser DOM to `chatgpt.com/c/…` + GitHub push + high-reasoning 5.6 Sol. Start with Muse before refining review. Includes full `meta` TOML and `requests` snippet. |
| 2 | 1,030 | **Secret handling policy:** `MUSE_API_KEY=...` $20 cap, "handle secrets however you feel comfortable," juice not worth squeeze. Use key freely while bootstrapping. |
| 3 | 1,616 | **Trust model:** *sand castle* not *sand box*; full permissions, yolo for Muse/Gemini, frozen VM state available elsewhere, GitHub/Google Drive backed up; "build what works best not what risks least," let Muse fail to discover failure modes. |
| 4 | 725 | Park Muse, focus on 3rd-party review; then assign tasks to evaluate stack and generalize. |
| 5 | 3,536 | **Review automation spec:** reviewer must be ≥ author (so 5.6 Sol high); manual workflow = push → `https://github.com/enigmatic-figure/PrologTsetlinMachine` + generic prompt → Firefox persistent login → remote clone + run → paste back. Now want Codex to own Firefox DOM itself. Includes example prompt URL `https://chatgpt.com/c/6a86f018-...`. |
| 6 | 492 | Google auth "browser may not be secure" + `https://support.google.com/accounts/answer/7675428` |
| 7 | 682 | Switch personal ↔ work ChatGPT Plus accounts; `https://chatgpt.com/c/6a86f018...` only on work; Chrome already open on work account |
| 8 | 1,136 | DOM hints: `+` button, `High` dropdown → `Advanced >` → model `5.6 Sol` / `5.5` / `o3`, checkmarks, reasoning slider |
| 9 | 843 | Watchdog hint: `Stop` circle-square vs submit up-arrow, 60s–15min variability, no static wait |
| 10| 586 | "Two new resources appear to be prototypes" — invite to propose more resources before real task |
| 11| 59 | "Alright my friend, its your system — go ahead and build it." — explicit build authorization |
| 12| 1,281 | **Test task:** onnx/safetensor → onnx sharding tool for memory-constrained conversion — "determine if problem is legitimate, if sharding is viable, if better alternative exists, then implement best plan." Random shardmill as probe of failure mode. |
| 13| 249 | Watchdog missed completion (44s review) — human interrupt |
| 14| 1,091| Satisfied but "you were two steps ahead" — review correctly scoped, didn''t build an OS around onnx; invite to adjust toolkit before next |
| 15| 134 | May publish repo remotely as you see fit |
| 16| 13,879 | **Meta-review:** other ChatGPT agent''s assessment of `onnx-shardmill` + toolkit dialog + repo, with 6 detailed recommendations: (1) workbench concurrency (load/save race, append-only ledger), (2) Muse job protocol (explicit `start/status/result/cancel` vs directory inference + exit-0-means-success), (3) context packets provenance (truncation/missing/ hash), (4) verification error handling (`FileNotFoundError` unreachable branch + base_commit drift), (5) learning as evaluation loop not just accumulation, (6) review failure evidence coupling. Plus "what not to change" (fresh vs continued conversations, workcells, `verify.toml`, recurrence threshold) and "break up `cli.py`" (45KB). Tests: "ugly" orchestration failures. CI note. Bottom line: toolkit graduated to *useful infrastructure prototype*; "make the workbench a rigorous closed-loop experimental system." |
| 17| 1,537 | "Glowing review" summary: stop architecting, instrumentation enough, evidence will tell; selective adoption, explicit deferral, regression testing, stopping decision — *that''s* the manager behavior you want |
| 18–21| 2,324–82 | Muse upgrade hints: structured output (constrained decoding), file handling (Files API), image/video/audio understanding, search grounding, tool search — plus cookbook `https://github.com/meta-models/meta-model-cookbook` and gated `MuseDocs/` dir |

Tool summary: **805 `exec`** — essentially the workbench itself. Final: native Meta Responses worker `muse_native.py:352` with durable `start/status/result/cancel`, strict JSON schema, reusable SHA-256 file uploads, workbench `delegate-muse-native` / `sync-muse-native` / `cancel-muse-native`, Codex Workbench 0.3.0, `codex-muse@personal 0.1.0+codex.20260820194013`, 19 Muse tests + 12 workbench tests passing, live enum-constrained JSON and image read via reused file ID, `completed_no_output` fixed.

### 2.2 How FormalPrompt would have performed

**Direct lineage.** This rollout *is* FormalPrompt''s own prehistory. The artifacts built here are the substrate FormalPrompt later compiled:

| Rollout artifact | FormalPrompt equivalent (current) |
|------------------|-----------------------------------|
| `codex-muse` runner (configurable path, `muse_agent.py`) | `formalprompt-muse-assistant` adapter (`FORMALPROMPT_MUSE_RUNNER`, `MUSE_REPO`, read-only, `--output-schema`, 262KB limits, 1MB library bound) |
| `codex-chatgpt-review` (DOM transport, model verification, Stop vs Copy detection, recovery) | *Not* bundled in FormalPrompt — review is now *provider-neutral JSON bridge* (`--reviewer-command` separate) and GitHub-backed independent review outside live canvas; the 15-min variability and `Stop` watchdog are correctly *not* reimplemented as a built-in browser — you own the transport |
| `codex-workbench` (objectives, decisions, tasks, workcells, `manifest.json`, `verify.toml`, learning observations) | `agent-workflow/v1` DAG (typed nodes, resources, scopes, joins) + `compiler.py` + `store.py` + `interventions.py` (sparse markers) + `git_lifecycle.py` (True Initialization). Workbench''s `load/save` race is fixed in FormalPrompt by revision-bound approval (`expected_revision` 409, state atomically replaced) and digest-bound verification — the exact fix reviewer #1 demanded for the append-only ledger |

In other words, the reviewer''s 6 recommendations from Prompt 16 are *visible* in what you shipped as FormalPrompt:

1. **Concurrency** — FormalPrompt uses `expected_revision` + atomic `document.json`/`state.json` replace + revision check; two concurrent writers cannot both win. Codex handled the `manifest.json` race correctly in the later session; our DAG''s `RevisionConflict` is the hardened version.
2. **Muse job protocol** — FormalPrompt''s `CommandAssistant` + `muse_runner` now has the durable `start → job_id → status/result/cancel` split reviewer #2 demanded; the old `delegate-muse` directory-inference + "exit 0 = success" is gone. Our new `muse Native Worker` note in the review answer mirrors this split.
3. **Context packet provenance** — reviewer #3 demanded truncation markers, requested/found/bytes/hash. FormalPrompt''s `CommandAssistant` bounds (1M stdout, 65K stderr, group kill) and `assistant.py`''s `CommandOutputLimitExceeded` plus the new `knowledge/canvas-field-patterns.md` that records `requested | found | total | supplied | hash` is the descendant of that fix. The old `## File: path` with silent prefix-only read is exactly what caused the prior bug.
4. **Verification error handling** — reviewer #4''s unreachable `FileNotFoundError` branch is why `store.py` + `cli.py` now wrap `FileNotFoundError` before `command()` and emit a failed-check summary with log paths, not a silent abort.
5. **Learning as closed loop** — reviewer #5 wanted `observation → candidate → guidance revision → evaluation cases → later outcomes → confirmed/regressed`. Our `docs/muse-tuning.md` now prescribes exactly that loop and the new `examples/muse-composer-evals.json` with invariant-based cases (`whole-graph-approval`, `review-repair-loop`, `parallel-subsystems`) is the behavioral regression harness the reviewer proposed.
6. **Review failure coupling** — reviewer #6 wanted `review.failed` events + screenshot/stderr + learning observation on nonzero exit. FormalPrompt''s `store.request_review` now records `failures/` + appends to `events.jsonl` and `interventions.py` would mark the sparse intervention, not silently raise.

Codex''s selective adoption after that meta-review is also the behavior FormalPrompt *wants* from a manager: "A self-modifying system that incorporates every plausible recommendation would deteriorate quickly. What we saw here was selective adoption, explicit deferral, regression testing, and a stopping decision." Our new `muse-facilitator.md` explicitly warns Muse *not* to add ornamental nodes or widen scope because it seems convenient — the same discipline.

**Where Codex handled these prompts better than FormalPrompt would have today:**

* **Incremental disclosure over 21 turns.** The user never gave a single spec — capability unfolded: first Muse (with TOML + example), then key ($20), then sandcastle trust, then park Muse, then review automation (with PrologTsetlinMachine example), then DOM hints, then account switch, then watchdog, then "go ahead and build it" after 10 prompts of context. FormalPrompt expects one *converged* `CanvasDocument` before compilation. To capture this session, Muse would have had to repeatedly return `needs-clarification` canvases (Muse TOML fields, secret-handling `select`, trust-policy `select` {`sandcastle` vs `sandbox`}, review DOM `select` {`firefox DOM` vs `direct API`}) — technically correct but the *user explicitly said* "we can leave Muse side for a moment" (Prompt 4) to sequence attention. FormalPrompt''s canvas can''t express "defer this tab''s decisions for now" without marking them `unresolved` blockers, which block approval. Codex handled the sequencing by deferring implementation, not by formal fields. Our DAG has `gate: user-approval` but not "defer this branch''s review until after the other branch''s demo." Lesson: we need a `defer` or `blocked-by` signal that isn''t a hard blocker.
* **"Max utility not minimal risk."** Prompt 3 is unambiguous: yolo, full permissions, frozen VM, do not encumber Muse with guardrails that hide failure modes. FormalPrompt''s security invariants (loopback-only, token in fragment, CSP `default-src ''self''`, RE2 only, read-only Muse, no inline scripts) are *correct* for a local browser canvas — but they *are* guardrails that hide failure modes. The library''s new `skill.browser-canvas` re-states those invariants as gospel, yet the user wants the opposite for this project. Our current `policy.deviation` allows *narrow* adaptation but not "give the agent real `rm -rf`." To honor this user we''d need a `policy.sandcastle` that *opts out* of restrictions and records that choice as intentional, so the audit index can later show why failures were allowed to be visible. We don''t have that policy — we have four restrictive policies.
* **Onnx-shardmill as probe vs deliverable.** Prompt 12 is deliberately ambiguous: "determine if problem is legitimate, if sharding is viable, or if better alternative exists, then implement best plan." Codex correctly treated investigation *as* the first node (research → decide) rather than pre-declaring "shard along natural boundaries." FormalPrompt''s `workflow` expects the plan to be fully declared before approval. Under our contract, Muse would have been forced to commit to "shard vs stitch vs alternative" in the DAG before seeing the repo. Codex''s approach — ephemeral researcher that can *replace* the plan — is more appropriate for a spike where the task is to *discover whether the task is worthwhile*. Our `prompt.research` now covers that, but we still force it to be a DAG node rather than a pre-canvas investigation.
* **Watchdog miss (44s) + human interrupt.** Prompt 13 shows the real watchdog failure mode. FormalPrompt''s `assistant.py` bounds (deadline + stream limit + group kill) and `muse_native.py`''s `completed_no_output` classification handle *provider-side* liveness, but the Chrome DOM "Stop vs Copy" liveness is out of scope — intentionally, because we moved review to a JSON bridge. That''s a conscious boundary, not a bug: the *next* session''s reviewer (Prompt 16) praised the new completion logic ("stable content + absence of Stop or presence of Copy") — that logic lives in `codex-chatgpt-review`, not in FormalPrompt. If a user *does* wire a DOM reviewer as `--reviewer-command`, our timeout + `CommandOutputLimitExceeded` will still correctly mark `failed` and emit an intervention marker rather than silently miss completion — which matches the human interrupt recovery here.

**What FormalPrompt would have done that was genuinely better:**

* **Make the "review must be ≥ author" explicit.** Codex wrote that as a belief in chat (Prompt 5). Our `policy.review-gate` and `ReviewWorkflowNode.independent_from` make it a *checkable invariant*: `independent: true` + `independent_from: [implement]` + `require_independent_review: true` digest-bound. The old toolkit couldn''t enforce it; now `validate_document` would reject a review that omitted its upstream.
* **Make the "fresh vs continued conversation" policy durable.** Codex organically discovered that fresh chats for milestone audits + continued chats for remediation was correct. FormalPrompt now encodes that as `review.remediation` with `maximum_rounds` + `exhaustion` — the exact behavior the reviewer said to preserve.
* **Make the 805 `exec` calls a reviewable plan.** The real session''s tool list is opaque from the user side. FormalPrompt''s graph would have rendered those 805 steps as ~8 nodes (`input: approved intent` → `agent: implement shardmill` → `operation: test` → `review: independent` → `gate: user-approval` → …) with `write_scope` disjointness checked, so parallel writers would not overlap. Codex''s later `cli.py` split (45KB → `state.py/events.py/tasks.py/workcells.py/context.py/muse.py/verify.py/review.py/learning.py/cli.py`) is exactly the mechanical separation our reviewer asked for — and our `templates/dag-patterns.md` now suggests that split as a node boundary.

### 2.3 Verdict for CLI tools

This session *produced the harness FormalPrompt is built on*. The outcomes were good precisely because Codex was allowed to be a manager with judgment: it built a real orchestration substrate, encoded lessons, deferred immature recommendations, and stopped. FormalPrompt''s current workspace is the *next* version of those tools with the reviewer''s 6 fixes built in. The gap that remains is not technical but *philosophical*: the user wants an agent that can be *maximally useful in a sandcastle* — FormalPrompt wants an agent that is *maximally verifiable in a sandbox*. Both are correct for different projects; our library now needs a way to let the *user* pick the pole via the canvas itself.

---

## 3. Cross-cutting lessons → concrete changes for FormalPrompt

### 3.1 What we changed in v0.2 because of these logs

We already shipped: `muse-facilitator.md` decision tree (needs-clarification vs ready), 33-entry library (6 DAG templates, 4 agents, 4 skills, 4 policies, 4 knowledge, 2 report templates), `canvas-field-patterns.md`, `agents-md-template.md`, `muse-tuning.md` history-informed loop, 132 tests + ruff + build green (5.2% of 1MB).

These directly address the 5-fix CoT spec (endpoint ablations, norm, `N_eff`, paired `W`/`G`, KV cache) and the 6-point meta-review (concurrency, durable job protocol, truncation provenance, verification errors, closed-loop learning, review failure coupling).

### 3.2 What these logs suggest we *still* need

1. **Lightweight/inquiry mode.**
   * Add a canvas-level flag `metadata.inquiry: true` (or `completion.require_formal_gates: false`) that demotes `unresolved` blockers from error to warning. Lets the CoT personal inquiry run without an extra clarification round, while the later above-reproach demonstration can require strict gates. Field: `select` {`inquiry: move needle fast`, `demonstration: above reproach`} with implications for verification depth.
   * Artifact: `policy.lightweight-inquiry` (`execution-policy`).

2. **Hardware/runtime as first-class capabilities.**
   * Add `tool.colab-cli` + `tool.kaggle-batch` + `tool.tpu-v5e` harness capabilities (pinned, `execution-preflight`) and a `skill.kaggle-batch` (allowlist, sharding, async `submit → poll → fetch`).
   * Add `knowledge.hardware-tradeoffs` (T4 2×15GB/30s queue vs v5e-1 1×16GB/20min queue vs Kaggle T4x2/30h/week). Then the TPU-vs-Kaggle choice becomes a `select` with real implications, not chat.
   * Template: `dag-colab-kaggle-campaign` (dual-T4 problem sharding, paired policies, pinned Hub revisions, SHA-256 exclusion, `holdout` untouched).

3. **Sandcastle/utility-max vs sandbox/safety-max as a declared policy.**
   * Add `policy.sandcastle-trust` (`execution-policy`): "This project runs in a sandcastle — full permissions, frozen VM snapshots, yolo — do not encumber Muse with guardrails that hide failure modes; emit `intervention` markers but do not block. Audit will later decide if failures were worth the speed."
   * Make `browser-canvas` skill conditional on that policy — permissive when sandcastle, restrictive when sandbox. This lets the user''s Prompt 3 be *declared* rather than implicit.

4. **Staged adaptive program as a DAG pattern, not just remediation.**
   * Add `template.dag-staged-adaptive` — Stage 1 static sweep (response curve, `α∈[0,.20]`, falsification at 0.20) → `gate: user-approval` (curve minimum stable + CIs) → Stage 2 narrow adaptive `δ_t = wᵀφ+b`. The gate consumes the *evidence* (ΔL table, Wilcox) as an `evidence` edge, not just a human yes. This is exactly the CoT Stage A/B you now need.

5. **Incremental disclosure handling.**
   * The 21-prompt CLI-tools brief arrived over 6 hours with deliberate sequencing ("park Muse," "here''s the PrologTsetlinMachine example," "here''s the DOM"). Our current `needs-clarification` can add 1–3 fields per round, but has no "defer this tab" language. Add guidance to `muse-facilitator.md`: when new information arrives that expands scope (e.g., "oh and there''s a work ChatGPT account"), treat it as a new `unresolved` decision attached to the affected tab rather than rewriting confirmed facts. The sparse-intervention marker is the runtime analogue; the canvas needs the design-time analogue.

6. **Mathematical spec fields.**
   * CoT specs are full of LaTeX (`E_t`, `w_i`, `N_eff`, `tilde h`). Our field `description` and `rationale` are plain text. We should explicitly allow and render `description` as Markdown+Math (rendered as `textContent` with KaTeX client-side, never as embedded HTML) so the 5 fixes remain readable in the browser. This is a small renderer change behind a `math: true` flag.

### 3.3 What Codex got right that we should preserve

* **Selective adoption, explicit deferral, stopping decision.** The glowing review''s last paragraph is the *right* manager instinct and it matches our whole-graph approval + intervention philosophy: don''t rewrite history to look planned; record the marker, keep Git and the session log as truth, reserve causal diagnosis for a high-context audit. Our `policy.deviation` and `docs/muse-workspace-design.md` already say this — don''t add a "fix everything" policy.
* **"Inspect repo then decide" for research spikes.** For a spike whose purpose is *to discover whether the task is worthwhile* (onnx shardmill), a pre-declared DAG is premature. Preserve the `research` → *decide* → `implement` flow, and let `prompt.research` be the legitimate first node.
* **Workbench as durable state outside context window.** The reviewer''s bottom line — objective/decisions/tasks/artifacts/patches/verification/reviews/checkpoints/observations existing *outside transient context* — is FormalPrompt''s `store.py` + `compiler.py` + `artifacts/manifest.json`. Don''t regress to shell transcripts.

---

## 4. Bottom line

Both sessions were successful *because* Codex behaved like a collaborator with judgment, not a form-filler:

* **CoT** — Codex patched the doc, ran the broad search, then narrowed based on real holdout loss (`W`, `G`, response curve) without forcing an extra formal round when the user wanted speed. FormalPrompt would have made the static 6.9% result *more credible* (paired CIs, exact exclusions, pinned revisions), but would have added friction to the "personal inquiry" preamble. The fix is a lightweight mode and a staged-adaptive template.
* **CLI tools** — Codex built a real substrate with clean boundaries, encoded lessons, and stopped when instrumentation was sufficient. FormalPrompt is the *next* version of that substrate with the reviewer''s 6 fixes built in. What remains is to let the user declare "sandcastle vs sandbox" and to support incremental disclosure without rewriting confirmed facts.

You now have a Muse Spark seat that knows how to ask the *right one question* before composing, and how to compose a *whole-graph* plan when the spec is ready — and it has the templates to render that plan as a browser DAG you can verify spatially, which is exactly the cross-modal insight from your C++ mock-up writ large.

If you want, I can materialize the 6 artifacts above (`kaggle-batch`, `sandcastle`, `staged-adaptive`, `hardware-tradeoffs`, `lightweight-inquiry`, `math rendering`) into the library now and cut the next `needs-clarification` canvas against the CoT Stage B prompt as a dogfood pass.

