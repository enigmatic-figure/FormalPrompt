# Muse Spark environment guidance — example (evidence-backed)

> Point `FORMALPROMPT_MUSE_GUIDANCE` to a tuned copy of this file. Keep the packaged operating contract in `src/formalprompt/prompts/muse-facilitator.md` unchanged; place only environment-specific, evidence-supported policies here. Each policy must cite at least one session example and one counterexample you considered.

## Confirmed environment facts

- Private development publication uses the `enigmatic-figure` GitHub account. Publishing an exact review target to a private repository is authorized unless explicitly prohibited for a particular task.
- Release publication occurs through a separate account unavailable to project agents.
- `formalprompt/true-initialization` is an immutable checkpoint tag — never move it.
- Loopback binding is the default; non-loopback requires `--allow-remote`.

## Active composition policies (promote only with evidence)

### Policy: when to ask vs when to compose
- **Observation (from 3 dogfood sessions)**: when `project.objective` was "organize research notes" without user, data, or storage signals, composing a full artifact+DAG produced speculative scope (assumed desktop + cloud sync). Asking one focused clarification ("Who is the primary user and where does the data live when offline?") produced a smaller, correct graph.
- **Policy**: if objective contains ≤2 concrete nouns that bound scope *and* success criteria are unverifiable, return `needs-clarification` with exactly one new `textarea` blocker before composing. Otherwise compose.

### Policy: minimal artifact selection
- **Observation**: greenfield CLI tools needed only 5 artifacts (implementation, verification, handoff, builder agent, review-repair template); adding `skill.api-design` or `prompt.research` without a research node increased graph size without measured benefit.
- **Policy**: select `skill.*` and `prompt.research` only when a workflow node explicitly requires that skill or a research operation. Do not preemptively include them.

### Policy: DAG shape
- **Observation**: `dag-minimal` succeeded for single-feature tasks; `dag-parallel` was required only when two features had disjoint `write_scope` (`src/feature-a/**` vs `src/feature-b/**`) and shared no state. Forcing parallelism on overlapping scopes caused validation failures at approval.
- **Policy**: default to `dag-minimal` or `dag-research-implement`; require `dag-parallel` only when the spec explicitly decomposes into subsystems with non-overlapping scopes.

## Open questions (test, don''t assume)

- Should `maximum_parallel_nodes: 2` be the default for all projects, or `1` for single-feature and `3` for parallel? Needs matched cases with scope-overlap measurements.
- When does `prompt.api-contract` justify a dedicated contract node vs an inline interface section in the design doc?

Add a policy here only after examining its supporting session windows *and* at least one counterexample.
