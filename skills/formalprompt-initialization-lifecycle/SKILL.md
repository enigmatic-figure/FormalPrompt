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

Preserve the reviewed initialization state separately from later project execution, then use the
resulting diff and structured learning records to improve reusable initialization assets.

## When to Use

- An approved FormalPrompt run produced prompts, agent definitions, skills, research requests, or
  governance files that should initialize a project.
- The user requests independent GitHub-backed review of project initialization.
- Execution forced a corrective change to an initialization artifact.
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
5. During execution, when a prompt, skill, template, still, or governance weakness causes a
   corrective change, run `formalprompt learn <project-directory> --artifact ... --problem ...
   --adjustment ... --recommendation ... --evidence ...`. Commit the append-only
   `.formalprompt-learning.jsonl` ledger with the correction.
6. At completion, run `formalprompt retrospective <project-directory>`. Review both
   `INITIALIZATION_RETROSPECTIVE.md` and `INITIALIZATION_RETROSPECTIVE.patch`.
7. Apply confirmed lessons to the reusable initialization templates or assets as a separate,
   reviewed change. Preserve the original True Initialization tag as historical evidence.

## Pitfalls

- Do not checkpoint an uncommitted or pre-review state.
- Do not force-move or recreate an existing True Initialization tag.
- Do not treat a private development push as a release publication.
- Do not record generic implementation changes as initialization failures; use the learning ledger
  when an initialization artifact actually required correction.
- Do not materialize a bundle whose terminal state, manifest membership, hashes, approval revision,
  or approved document digest fail verification.

## Verification

- The materialized files match the compiled manifest and remain inside the target project.
- The independent review and confirmed repairs are committed before checkpointing.
- `formalprompt/true-initialization` resolves to the reviewed-and-repaired clean commit and exists on
  the private origin when `--push` was used.
- The retrospective names the exact baseline and completion commits, includes a full patch, and
  highlights initialization-sensitive changes plus structured learning records.
