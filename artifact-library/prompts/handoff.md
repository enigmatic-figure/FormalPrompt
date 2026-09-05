# Verified handoff — compact, no deliberation import

Assemble the verified deliverables for the primary agent or user without importing initialization deliberation.

Steps:
1. Confirm `formalprompt result` verification passed (`contract: agent-canvas-result/v1`, `status: compiled`, `result.handoff`, `result.workflow`/`execution_contract` if present, manifest hashes). Stop if verification rejects.
2. Read only the declared handoff file (`EXECUTION_BRIEF.md` or `artifacts/initialization/<primary_artifact>` when graph-backed) and, when needed, `SPECIFICATION.md`/`specification.json` for a missing detail. Do not load `events.jsonl`, `requests/`, or assistant transcripts.
3. Summarize: what was delivered, verification status and evidence pointers, immutable Git checkpoint (if any), and any `unresolved_count` decisions the user must still make.
4. Never claim completion until every declared `completion_nodes` has satisfied inputs and its acceptance evidence is durable. Provide paths, not assertions.

Handoff text should fit in one brief document. The caller should be able to start work from this brief alone.
