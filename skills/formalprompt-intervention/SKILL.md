---
name: formalprompt-intervention
description: Mark a local FormalPrompt execution intervention.
license: MIT
---

# FormalPrompt Intervention

Add one sparse correlation marker when violated runtime expectations require a local intervention.
The marker joins the approved workflow, session log, and Git without asking the execution agent to
diagnose the generating system.

## When to Use

- Physical project state requires a local repair or adaptation during an approved workflow node.
- The event may deserve later high-context examination of initialization policy or artifacts.
- Do not use for ordinary planned implementation work or to propose an upstream change.

## Procedure

1. Preserve the approved graph and identify the currently active graph node.
2. Run `formalprompt intervene <run-directory> --node <node-id> --project
   <project-directory> --json` once for the local intervention. If the harness supplies a session
   event ID, pass it with `--session-event`; otherwise retain the generated correlation ID in the
   command output.
3. Repair the local project within the node's approved authority and continue toward its original
   acceptance criteria.
4. Do not add a root-cause hypothesis, category, durability recommendation, or explanatory ledger
   entry. A later high-context auditor owns those judgments.

## Pitfalls

- Do not edit the approved workflow to make the intervention appear planned.
- Do not invoke this skill for every command, failed attempt, or normal implementation choice.
- Do not promote a local repair into reusable prompts, skills, templates, or policy during execution.
- Do not create a parallel narrative when Git and the session log already preserve the evidence.

## Verification

- The command returns `formalprompt-intervention-flag/v1` with only the run ID, graph node, session
  event, Git head, skill version, and timestamp in addition to its contract.
- The marker appears as `intervention.flagged` in the run's existing `events.jsonl` stream.
- The approved workflow artifact remains unchanged.
