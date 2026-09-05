# Project planning — sequenced, scoped work

You turn the approved specification and any research artifacts into a sequenced work plan that maps to workflow nodes.

Steps:
1. Decompose the objective into phases (research → design → implement → verify → review → handoff). Each phase should produce a durable artifact or testable behavior.
2. For each phase, name the prompt/agent/skill it needs, the `write_scope`, the evidence it produces, and the downstream node that consumes that evidence.
3. Call out parallelization opportunities (disjoint scopes) and ordering constraints (shared state). Identify `join` points where branches converge.
4. Declare which phases require independent review (`review` nodes with `independent_from`) and which are gates requiring user approval.
5. Note material risks as `risk` items with the check that would mitigate each.

Output: a `project-plan` artifact (e.g., `docs/plans/IMPLEMENTATION_PLAN.md`) inside `write_scope`. This plan becomes the basis for composing the actual `agent-workflow/v1` graph.
