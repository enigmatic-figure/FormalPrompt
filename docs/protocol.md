# Agent Canvas Protocol v1

## Envelope

A canvas document is UTF-8 JSON with this top-level shape:

```json
{
  "protocol": "agent-canvas/v1",
  "kind": "formalprompt/specification",
  "metadata": {
    "title": "Project specification",
    "description": "Review the agent's interpretation before execution",
    "created_by": "primary-agent"
  },
  "tabs": [],
  "completion": {
    "require_user_approval": true,
    "require_independent_review": false
  },
  "initialization": {
    "primary_artifact": null,
    "artifacts": []
  }
}
```

Unknown properties are rejected in protocol-owned objects. This prevents misspelled or unsupported directives from silently changing meaning.

## Structure

A document contains ordered tabs. Tabs contain ordered sections. Sections contain ordered fields. Every tab, section, and field ID is unique within its namespace. Field IDs should be stable dotted identifiers such as `runtime.browser.graphical`.

## Field types

Version 1 supports:

- `text`
- `textarea`
- `number`
- `checkbox`
- `select`
- `multiselect`

Select fields contain options with machine values, human labels, and optional implications. Values are JSON primitives or arrays appropriate to the field type.

## Field semantics

Each field records independent semantic dimensions:

- `provenance`: `explicit`, `inferred`, `proposed`, `user-confirmed`, or `unresolved`
- `review_status`: `unreviewed`, `accepted`, `rejected`, `needs-input`, or `conflict`
- `importance`: `blocker`, `high`, `normal`, or `low`
- `confidence`: optional number from 0 through 1
- `rationale`: optional explanation of an inference or proposal

A renderer must expose these semantics in text and may additionally use color. A user edit changes provenance to `user-confirmed` and review status to `accepted`.

## Initialization artifacts

The optional `initialization` plan contains staged files produced after specification convergence.
Each artifact has a stable ID, safe relative POSIX path, kind, title, content, provenance, review
status, importance, and rationale. Supported kinds are `primary-prompt`, `agent-definition`,
`skill`, `research-request`, `knowledge-base-plan`, `project-plan`, and `other`.

`primary_artifact` names the artifact that becomes the result handoff. Paths are resolved beneath
`artifacts/initialization/`; absolute paths, backslashes, traversal segments, duplicate paths, and
unknown primary IDs block approval. Initialization content is canonical document state, so a user
edit advances the revision and invalidates prior approval.

## Validation

Structural validation checks protocol shape and types. Semantic validation checks unique IDs, option
membership, required values, finite numeric inputs, validation constraints, unresolved blockers,
and conflicts.

`validation.pattern` is a server-enforced RE2 full-match expression limited to 512 characters.
RE2 provides linear-time matching and rejects backreferences, look-around, and other constructs that
require backtracking. The browser never receives the expression as an HTML `pattern` attribute;
server validation is authoritative for both stored updates and approval readiness.

Readiness for approval requires no error-level semantic issues. Approval records the revision and
SHA-256 digest of the canonical JSON document. Compilation recomputes both, so changing
`document.json` outside the broker cannot reuse an earlier approval.

Approval is whole-document confirmation, not a collection of per-field or per-node authorization
seals. Provenance remains useful for inspecting how pre-approval content arose, while the approved
digest affirms the effective fields, initialization artifacts, workflow nodes, resource bindings,
edges, boundaries, and policy together. Any authenticated user edit advances the revision and
invalidates that approval before the changed document can be compiled.

`require_user_approval` is always true in v1. When `require_independent_review` is true, readiness
also requires a critic response with `disposition: ready` and no replacement document, recorded for
the exact current revision. Any later field, artifact, or proposal edit invalidates that review.

## Events

Every accepted mutation appends a JSON Lines event with:

- monotonically increasing revision
- timestamp in UTC
- event type
- actor (`user`, `agent`, or `system`)
- target identifier
- mutation summary

Secrets and access tokens must never appear in events.

## Assistant request contract

A command agent receives one JSON object on standard input:

```json
{
  "contract": "agent-canvas-assistant/v1",
  "request_id": "...",
  "operation": "field-assistance",
  "context": {
    "document_title": "...",
    "field": {},
    "question": "Explain the implications of these options"
  }
}
```

It writes exactly one JSON object to standard output:

```json
{
  "contract": "agent-canvas-assistant/v1",
  "request_id": "...",
  "summary": "...",
  "suggestions": [
    {
      "value": "...",
      "label": "...",
      "implications": "..."
    }
  ],
  "questions": [],
  "disposition": "advisory",
  "next_document": null
}
```

For `specification-review` and `initialization-compose`, `next_document` may instead contain a
complete canvas defining another focused clarification round or adding initialization artifacts.
`disposition` is `advisory`, `needs-clarification`, or `ready`. A next document is a proposal, not
canonical state; the user must apply it against the source revision, and stale proposals are
rejected.

A ready initialization may also carry an `agent-workflow/v1` object. It is an acyclic, typed,
resource-referenced blueprint that the user can inspect and edit before approval. See
`docs/workflow-protocol.md` for its node kinds, invariants, compilation contract, and sparse
intervention-correlation model.

Assistant failures are recorded and returned as failures; they never block ordinary editing or
corrupt the canonical document.

## Result contract

A compiled run returns:

```json
{
  "contract": "agent-canvas-result/v1",
  "run_id": "...",
  "status": "compiled",
  "revision": 1,
  "document_sha256": "...",
  "unresolved_count": 0,
  "artifacts": {},
  "handoff": "artifacts/initialization/prompts/PRIMARY_AGENT.md",
  "workflow": "artifacts/workflow.json",
  "execution_contract": "artifacts/EXECUTION_CONTRACT.md"
}
```

Paths are relative to the run directory in persisted manifests. A result is consumable only when
state is terminal and the state approval, result, manifest, specification, current document, file
membership, sizes, hashes, and declared handoff all verify. CLI output may additionally include the
absolute run-directory path.

The workflow fields appear only when the approved document contains a workflow. Their files are
manifest members and the verifier also checks the compiled graph, approved digest, resource paths,
resource hashes, and pinned capabilities.
