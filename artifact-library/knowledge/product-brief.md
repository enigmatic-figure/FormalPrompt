# Knowledge: Product brief — concise context for agents

## Purpose
Carry the product boundary and user intent into each scoped agent without re-sending the full specification conversation.

## Template
- **One-sentence purpose**: what the product does for whom.
- **Non-goals**: explicit exclusions from `project.out_of_scope`.
- **Constraints**: platform, runtime, delivery form, compliance boundaries that affect design.
- **Acceptance criteria**: 3–7 observable checks that define done.
- **Glossary**: terms and IDs the spec uses (field IDs, workflow node IDs).

## Usage
Materialize per-project by adapting this template, then bind as a `knowledge` resource referenced by `input` or `agent` nodes. Keep it <1 page. It is the `input` node''s artifact for "approved intent."
