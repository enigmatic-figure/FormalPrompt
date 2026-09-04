# Initialization lifecycle

FormalPrompt separates project initialization from project execution. Runtime capture is limited to
correlation bookmarks; causal analysis belongs to a later review that can see the complete generating
system.

## Lifecycle

```text
CANVAS ITERATION
  -> USER-APPROVED INITIALIZATION BUNDLE
  -> MATERIALIZED PROJECT FILES
  -> PRIVATE DEVELOPMENT COMMIT
  -> INDEPENDENT REVIEW + CONFIRMED REPAIRS
  -> TRUE INITIALIZATION TAG
  -> PROJECT EXECUTION + SPARSE INTERVENTION FLAGS
  -> COMPLETION COMMIT
  -> AUDIT INDEX + FULL GIT DIFF
  -> SEPARATE HIGH-CONTEXT CAUSAL REVIEW
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

## Mark a local intervention

When physical project state requires a local repair or adaptation worth examining later, identify
the active approved graph node and invoke the intervention skill:

```text
formalprompt intervene <run-directory> \
  --node implement \
  --project <project-directory> \
  --json
```

This appends `formalprompt-intervention-flag/v1` to the run's existing event stream. The marker holds
only the run, graph node, session correlation ID, Git head, skill version, and timestamp. It contains
no diagnosis, category, narrative, or upstream recommendation. Git preserves what changed, the
session log preserves execution, and the approved graph preserves intended context and authority.

## Build the audit index

At completion, create a compact index:

```text
formalprompt audit-index <run-directory> \
  --project <project-directory> \
  --session-log <session-log>
```

The collector locates intervention flags and records pointers to their event lines, approved graph
nodes and resources, bounded session-log line ranges, Git commits and diff ranges, and the immutable
initialization sources. It deliberately does not copy session windows or Git diffs into another
history and makes no causal claim. Run it with `--force` only to refresh an existing index.
When a session log is supplied, collection fails if any marker's correlation ID is absent; an
incomplete session bookmark is never published as a successful index.

## Compare completion with initialization

After committing the completed project:

```text
formalprompt retrospective <project-directory>
```

The command verifies that True Initialization is an ancestor of the completion commit and writes:

- `INITIALIZATION_RETROSPECTIVE.md`: commits, file summary, and highlighted
  changes to prompts, skills, templates, stills, assets, Markdown, and agent-governance files.
- `INITIALIZATION_RETROSPECTIVE.patch`: the complete binary-safe Git diff from True Initialization
  to completion.

The report is a mechanically derived Git comparison, not a diagnosis. A later high-context auditor
can correlate it with the intervention index, session logs, approved graph, initialized artifacts,
model assignments, and complete generating system. Never move the historical checkpoint to make the
diff smaller.
