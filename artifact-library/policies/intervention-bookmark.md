# Runtime intervention bookmark

Git records what changed. The harness session log records what the execution agent encountered and did. The approved graph records intent, context, resources, and authority.

When violated expectations require a meaningful local intervention, append one `formalprompt-intervention-flag/v1` marker that joins those sources. Do not add a root-cause hypothesis, category, narrative history, or durability recommendation during project execution. Those judgments belong to a later high-context audit with the complete generating system available.

Use `formalprompt intervene --node <active-node-id> --project . --session-event <event-id>` once per intervention. Preserve the repair in Git; do not rewrite the approved graph.
