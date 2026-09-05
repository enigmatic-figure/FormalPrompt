# Report template: Handoff manifest

## Purpose
Return verified deliverables, evidence pointers, and unresolved decisions in one brief document.

## Sections
- **Deliverables**: paths to implementation files, tests, docs produced inside the run''s `write_scope`s.
- **Verification summary**: per-node criterion table with verdict and evidence pointer.
- **Immutable checkpoint**: Git commit/tag and branch that was reviewed (if applicable).
- **Manifest**: `artifacts/manifest.json` excerpt (paths, sizes, hashes).
- **Unresolved decisions**: `unresolved_count` and the questions the user must still answer.

## Notes
- Cite `formalprompt result` output, not manual claims.
- Never import facilitator transcripts or session logs by default.
- Keep the handoff to ≤2 pages; link to detailed reports where needed.

Kind: `report-template`. Referenced by `handoff` operation nodes.
