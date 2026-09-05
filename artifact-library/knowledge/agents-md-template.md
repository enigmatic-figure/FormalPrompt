# Knowledge: AGENTS.md template for a FormalPrompt-managed project

## Purpose
This is the repository''s steering file that scoped agents (Codex, verifier, researcher) see when they open the project. It is *not* the initialization conversation. Copy and adapt this template into the project''s `AGENTS.md` as an initialization artifact when the workflow requires it.

## Template — adapt to your project
```markdown
# Project instructions for agents

## Identity
<one-sentence purpose: what the product does for whom>

## Constraints
- Write only inside your node''s `write_scope`. Never widen scope without user approval.
- Preserve behavior outside scope. Keep changes cohesive and minimal.
- Keep secrets out of files and git history.

## Verification
<how to verify: e.g., `uv run pytest -q`, `ruff check`, `node --check`>

## Workflow authority
The approved `workflow.json` and `EXECUTION_CONTRACT.md` are the source of truth. Do not rewrite the graph to make history look planned. Treat `REVIEW.md` and `EXECUTION_CONTRACT.md` as your primary context — not the facilitator transcript.

## Intervention bookmark
When physical state requires a local intervention worth later examination, emit one `formalprompt-intervention` marker with the active node ID, then continue toward acceptance criteria. Do not diagnose the generating system or propose upstream policy changes during execution.

## Completion
Completion requires every declared `completion_nodes` to have evidence. Do not claim completion until verification passes and the handoff manifest verifies.
```

## Usage
Materialize as a `knowledge-base-plan` artifact (e.g., `knowledge/AGENTS.md.template`) and reference it from `input` or `agent` nodes via `context_resources` when the project needs durable agent steering. Keep the repository''s real `AGENTS.md` inside an appropriate `write_scope` (often `AGENTS.md` at root or `src/**` only if scoped).

Customize the placeholders — don''t ship the template verbatim.
