# Initialization lifecycle

FormalPrompt separates project initialization from project execution so teams can inspect what the
initialization process got right, what execution later had to correct, and which reusable assets
should improve.

## Lifecycle

```text
CANVAS ITERATION
  -> USER-APPROVED INITIALIZATION BUNDLE
  -> MATERIALIZED PROJECT FILES
  -> PRIVATE DEVELOPMENT COMMIT
  -> INDEPENDENT REVIEW + CONFIRMED REPAIRS
  -> TRUE INITIALIZATION TAG
  -> PROJECT EXECUTION + LEARNING RECORDS
  -> COMPLETION COMMIT
  -> RETROSPECTIVE REPORT + FULL DIFF
  -> SEPARATE IMPROVEMENT TO REUSABLE ASSETS
```

The True Initialization checkpoint is the clean commit after independent review and repair, before
the implementation phase begins. FormalPrompt records it with the annotated Git tag
`formalprompt/true-initialization`. The tag is immutable historical evidence, not a release tag.

## Materialize the initialization bundle

```text
formalprompt materialize <run-directory> <project-directory>
```

Materialization verifies terminal state, result and manifest contracts, approval revision, canonical
document digest, exact manifest membership, artifact sizes, SHA-256 hashes, and the declared handoff.
It copies only entries beneath `artifacts/initialization/`, rejects paths that escape the target or
enter Git/FormalPrompt internal directories, and refuses to replace existing files unless `--force`
is explicit.

Inspect and commit the resulting project state. For GitHub-backed independent review, push the exact
commit to the private development repository before requesting review.

## Record True Initialization

After the independent reviewer passes the repaired initialization commit:

```text
formalprompt checkpoint <project-directory> \
  --run-directory <run-directory> \
  --push
```

The command requires a clean committed working tree, annotates the tag with the commit, branch,
origin, timestamp, and optional FormalPrompt run identity, then optionally pushes the branch and tag.
It refuses to replace an existing checkpoint tag.

## Capture corrections during execution

Record a learning only when project execution demonstrates that an initialization artifact needed a
behavioral correction:

```text
formalprompt learn <project-directory> \
  --artifact AGENTS.md \
  --problem "Two agents edited the same subsystem" \
  --adjustment "Assigned non-overlapping file ownership" \
  --recommendation "Make ownership mandatory in generated worker prompts" \
  --evidence "The repaired run completed without conflicts"
```

Records append to `.formalprompt-learning.jsonl`. Commit the ledger alongside the corrective change.
Ordinary implementation changes are not initialization learnings.

## Compare completion with initialization

After committing the completed project:

```text
formalprompt retrospective <project-directory>
```

The command verifies that True Initialization is an ancestor of the completion commit and writes:

- `INITIALIZATION_RETROSPECTIVE.md`: commits, file summary, structured lessons, and highlighted
  changes to prompts, skills, templates, stills, assets, Markdown, and agent-governance files.
- `INITIALIZATION_RETROSPECTIVE.patch`: the complete binary-safe Git diff from True Initialization
  to completion.

The learning ledger must remain append-only. Confirmed improvements belong in a new reviewed change
to the reusable initialization system; never move the historical checkpoint to make the diff smaller.
