# Agent Workflow Protocol

FormalPrompt's agent-workflow/v1 object is the user-editable execution blueprint inside an agent-canvas/v1 specification. It is declarative: the browser edits it, the broker validates it, and the compiler binds it to approved resources. It does not execute agents or commands.

## Sources of truth and correlation

1. The specification records user intent, assumptions, constraints, and acceptance criteria.
2. The approved workflow blueprint records the planned nodes, dependencies, authority, resources, checkpoints, and policies.
3. Git records changes and the harness session log records runtime activity and reasoning.
4. A sparse intervention marker joins those sources when a local repair may merit later examination.

The blueprint must not be rewritten to make runtime history look planned. FormalPrompt does not
create a parallel narrative history: an intervention marker contains only correlation coordinates.
Diagnosis and reusable-system recommendations belong to a later high-context audit.

## Resources

Every dependency used by a node is named in the graph resource registry.

- initialization-artifact binds to a typed file staged in the canvas. Compilation resolves it to a bundle-relative path and SHA-256 digest.
- harness-capability declares a runtime feature such as a terminal and its required interface version. Compilation pins that declaration; the execution harness must resolve and verify availability during preflight.

Resource kinds are prompt, agent-definition, skill, tool, template, knowledge, policy, and report-template. Nodes refer to resource IDs, never inline executable content.

## Nodes

| Kind | Purpose | Important declarations |
| --- | --- | --- |
| input | Introduce approved intent or context | resource IDs |
| artifact | Read, produce, or transform a resource | resource ID and mode |
| agent | Delegate bounded work | model, prompt, agent definition, context, skills, tools, write scope, criteria, timeout, budget |
| operation | Perform a bounded harness activity | research, test, report, materialize, checkpoint, or handoff; resource IDs, write scope, timeout, and criteria |
| review | Obtain independent judgment | model, prompt, subjects, evidence, upstream agents, bounded remediation |
| gate | Require a decision or proof | user approval, verification, or policy criteria |
| join | Synchronize branches | all or any strategy |

Each node has a stable ID, visual position, typed input and output ports, provenance, review state, importance, and rationale. Position is presentation metadata and does not affect execution.

## Edges and readiness

Edges connect one declared output port to one declared input port of the same data type:

- control sequences authorization to proceed;
- context supplies bounded informational input;
- artifact carries a produced durable resource;
- evidence carries verification or review proof.

Except for the any-join rule below, a node is ready only when each required input port is satisfied. An input port accepts one edge unless multiple is true. A runtime may schedule independent ready nodes concurrently up to maximum_parallel_nodes.

Join inputs are required, single-cardinality control ports. An all join becomes ready only after
every declared input edge succeeds. An any join becomes ready after the first successful input and
ignores later inputs. It does not cancel upstream work: those nodes continue according to their
other graph dependencies. If no input succeeds, the any join fails after every input becomes
terminal. This local input policy gives fan-out DAGs one deterministic meaning without requiring an
implicit cancellation region.

## Graph invariants

Semantic validation blocks approval when:

- a resource, node, edge, or port ID is duplicated;
- a resource reference is missing, incompatible, or an unpinned capability;
- an edge endpoint or port is absent or type-incompatible;
- a required input is disconnected or exceeds its cardinality;
- the graph contains a cycle;
- an entry has incoming edges or a completion has outgoing edges;
- a node is unreachable from every entry or cannot reach a completion;
- an agent write scope is unsafe;
- potentially concurrent writer nodes have overlapping write scopes;
- a node remains unresolved, rejected, conflicting, or needs input.
- a review fails to declare independence from every upstream agent.

Write scopes use a deliberately restricted repository-relative grammar. A path begins with a
literal segment, may contain literal or whole-segment star segments, and may end with a recursive
double-star segment. Partial wildcards, question marks, character classes, brace expressions,
escapes, absolute paths, parent traversal, Windows separators, .git, and .formalprompt are
rejected. Scope intersections use this same grammar and conservatively block parallel writers when
their intersection cannot be proven empty. An empty scope is read-only.

Write serialization uses a must-happen-before relation derived from required inputs, not ordinary
graph reachability. For an any join, only predecessors common to every input branch must precede
its descendants; a writer on one possible input branch may overlap work released by another and is
therefore treated as potentially concurrent.

Report, materialize, and handoff operations require a nonempty write scope. A checkpoint operation
does not receive filesystem authority; it must use a separately pinned git-checkpoint capability.

## Reviews and repair

The declared graph remains acyclic even when a project expects review-repair iterations. A review node carries a maximum number of rounds, a repair template resource, and an exhaustion action. At runtime, each repair is a new forward-only attempt linked to the failed review. This preserves the immutable user-approved intent while Git and the harness session log retain what occurred.

## Compilation

An approved graph produces:

- artifacts/workflow.json using agent-workflow-compiled/v1;
- artifacts/EXECUTION_CONTRACT.md for the primary execution agent.

The compiled object contains the exact approved graph, approved document digest, and resolved resources. Initialization artifacts resolve to content hashes; harness capabilities resolve to declared capability names and required interface versions. Both outputs are members of the digest manifest and are checked by the strict result verifier.

The run directory is the local trust boundary. The manifest is not a digital signature and does not
establish authenticity against an actor that can replace the entire run directory. Within that
boundary, verification checks approval/digest consistency and deterministically re-derives the
compiled outputs. Capability availability is an execution-preflight responsibility.

## Browser editing

The Workflow tab renders the DAG on a scrollable canvas. Users can select and inspect nodes, edit complete node declarations, move nodes by pointer or keyboard, add nodes, connect compatible ports, remove non-boundary nodes or edges, and arrange the graph by dependency level. Every save uses optimistic revision control, invalidates earlier approval and review, and runs server-side validation.

The editor renders agent-authored values as text and JSON data. It does not evaluate graph content as HTML or JavaScript. Moving or arranging nodes changes presentation state only. A newly added node begins unresolved and becomes user-confirmed only when the user explicitly saves its declaration. The broker owns this badge transition and rejects attempts to mint protected provenance through an assistant proposal or ordinary graph save.

Node provenance is a pre-approval authorship and review cue, not an independent authorization seal.
The authenticated workflow endpoint is the user-operated editing surface, so graph edits may change
nodes, connections, resources, bindings, boundaries, and policy. Every such save advances the
revision and clears earlier approval and independent review. Approval of the exact canonical
document digest is the authoritative user confirmation of the complete graph: every node and its
effective resources, edges, and policy are affirmed together regardless of its earlier provenance
badge. Compilation accepts only that approved digest.

Assistant replacement proposals expose their complete JSON and a structural change summary before
the Apply action. The broker rejects any proposal that changes or deletes explicit or
user-confirmed fields, initialization artifacts, workflow nodes, incident edges, referenced
resources, boundary membership, or workflow policy. Such changes require a direct user edit or a
new unresolved decision.
