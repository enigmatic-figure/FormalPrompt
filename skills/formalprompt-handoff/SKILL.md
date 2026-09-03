---
name: formalprompt-handoff
description: Consume compiled handoffs without importing deliberation.
license: MIT
metadata:
  hermes:
    tags: [Handoff, Context Budget, Artifacts, Verification]
    related_skills: []
---

# FormalPrompt Handoff Skill

Consume an approved FormalPrompt result as a compact execution contract. Preserve the context saving achieved by external deliberation: load the execution brief and only the specification details needed for the current work.

## When to Use

- A FormalPrompt process emitted an `agent-canvas-result/v1` completed event.
- The user asks the primary agent to begin execution from a compiled run.
- A resumed session needs to recover the final specification without replaying clarification dialogue.
- Do not use when the run lacks `result.json` or remains unapproved.

## Prerequisites

- The exact run directory comes from the ready or completed lifecycle event.
- `result.json`, `artifacts/manifest.json`, and the declared handoff file exist under that run directory.
- Any operation that copies generated files into the project is separately authorized by the user or original task.

## Procedure

1. Read `result.json` with `read_file`. Confirm `contract` is `agent-canvas-result/v1`, `status` is `compiled`, and `unresolved_count` is acceptable for the requested work.
2. Read `artifacts/manifest.json`. Resolve every artifact path relative to the run directory and reject any path that escapes it.
3. Verify file hashes through the `terminal` tool using the platform's available SHA-256 command or a short Python `hashlib` invocation. Confirm every declared file matches before trusting the handoff.
4. Read the handoff path declared by `result.json`. For an initialization package this may be a primary prompt beneath `artifacts/initialization/`; otherwise it is normally `artifacts/EXECUTION_BRIEF.md`. Load `artifacts/SPECIFICATION.md` or `specification.json` only when a required detail is absent from the declared handoff.
5. Do not load `events.jsonl` or assistant request/response files by default. Inspect them only when the user asks for an audit or a specific final decision cannot be explained from approved artifacts.
6. Translate the execution brief into the agent's normal task tracking and begin implementation. Preserve stated exclusions, acceptance criteria, and verification requirements.
7. Before reporting completion, compare the delivered work against the approved specification revision named in both result and manifest.

## Pitfalls

- A process exit is not proof of completion; only a compiled result is.
- Do not treat unresolved non-blocking fields as permission to invent consequential requirements.
- Do not copy `AGENTS.md`, skills, or other generated scaffolding into the project merely because it exists in the run bundle.
- Treat staged initialization files as proposals for execution setup, not authorization to install or execute them.
- Do not replace the user's original request with facilitator commentary; the approved specification is authoritative for refinements and the original request still governs anything it did not supersede.
- Hash verification proves artifact integrity, not that the user approved a different revision. Check the revision number too.

## Verification

- Result and manifest contracts are recognized and revisions match.
- Every declared artifact hash matches its file.
- The primary context receives the execution brief, not the deliberation ledger.
- Final work is checked against the approved acceptance criteria before completion is claimed.
