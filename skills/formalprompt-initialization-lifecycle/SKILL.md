---
name: formalprompt-initialization-lifecycle
description: Preserve and review initialization checkpoints.
license: MIT
metadata:
  hermes:
    tags: [Initialization, Git, Review, Retrospective]
    related_skills: [formalprompt-handoff]
---

# FormalPrompt Initialization Lifecycle Skill

Preserve the reviewed initialization state separately from later project execution, then make its
Git comparison and sparse intervention bookmarks available to a separate high-context audit.

## When to Use

- An approved FormalPrompt run produced prompts, agent definitions, skills, research requests, or
  governance files that should initialize a project.
- The user requests independent GitHub-backed review of project initialization.
- Execution required a local intervention worth correlating later.
- The project is complete and needs comparison with its True Initialization state.
- Do not use the checkpoint tag as a release tag or rewrite it to hide later changes.

## Procedure

1. Run `formalprompt materialize <run-directory> <project-directory>`. This verifies the compiled
   manifest, approval revision, and approved document digest before copying only
   `artifacts/initialization/**` paths. Inspect
   the resulting project diff before committing.
2. Commit the complete candidate initialization state and publish that exact commit to the private
   development repository when independent review is requested. In this environment, private
   publication to `enigmatic-figure` is standing authorized; public visibility is not implicit.
3. Run the independent review, repair confirmed findings, commit and push the repairs, then obtain
   a focused closure review against the new immutable commit.
4. From a clean working tree, run `formalprompt checkpoint <project-directory> --push`. The default
   annotated tag is `formalprompt/true-initialization`. Supply `--run-directory` when a compiled run
   should be recorded in the tag annotation.
5. During execution, use the `formalprompt-intervention` skill when physical project state requires
   a local intervention worth later examination. The execution agent records only the sparse marker.
6. At completion, run `formalprompt audit-index <run-directory> --project <project-directory>
   --session-log <session-log>` and `formalprompt retrospective <project-directory>`. Review the
   index alongside
   `INITIALIZATION_RETROSPECTIVE.md` and `INITIALIZATION_RETROSPECTIVE.patch`.
7. Give these artifacts and the complete generating system to a separate high-context auditor.
   Only that review should diagnose causes or recommend reusable-system changes. Preserve the
   original True Initialization tag as historical evidence.

## Pitfalls

- Do not checkpoint an uncommitted or pre-review state.
- Do not force-move or recreate an existing True Initialization tag.
- Do not treat a private development push as a release publication.
- Do not ask the project-execution agent for root-cause, categorization, or durability judgments.
- Do not duplicate Git or session history in an explanatory runtime ledger.
- Do not materialize a bundle whose terminal state, manifest membership, hashes, approval revision,
  or approved document digest fail verification.

## Verification

- The materialized files match the compiled manifest and remain inside the target project.
- The independent review and confirmed repairs are committed before checkpointing.
- `formalprompt/true-initialization` resolves to the reviewed-and-repaired clean commit and exists on
  the private origin when `--push` was used.
- The audit index points to intervention events, workflow nodes, session windows, and Git anchors
  without copying or interpreting their histories.
- The retrospective names the exact baseline and completion commits, includes a full patch, and
  explicitly avoids causal conclusions.
