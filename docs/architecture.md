# Architecture

## Product boundary

FormalPrompt is the reference application for Agent Canvas. Agent Canvas is responsible for local serving, rendering, state, validation, assistant requests, lifecycle, and result transport. FormalPrompt defines a specification-oriented schema profile and deterministic artifact compiler.

The canonical state is the canvas document. HTML, conversations, suggestions, and compiled prompts are projections of that document, never competing sources of truth.

## Components

### CLI

The CLI validates input, creates a durable run directory, starts the broker, waits for readiness, launches the selected renderer, and reports a machine-readable result. It must also support noninteractive validation and compilation.

### Broker

The broker binds to loopback by default and owns one run. It serves static UI assets and authenticated JSON APIs, serializes updates to the canonical document, appends events, evaluates readiness, dispatches optional command agents, and invokes compilers.

### Renderer

One semantic web application supports graphical Chromium-family browsers and Carbonyl. It uses keyboard-operable tabs, native controls, visible text labels, non-color provenance markers, and responsive layouts. Agent documents cannot inject JavaScript. A future freeform presentation canvas must run in a separate sandbox.

When a document contains an `agent-workflow/v1` blueprint, the renderer adds a scrollable node
graph and inspector. Node position is presentation state; node declarations, typed ports, edges,
resources, and policies remain canonical data and every graph edit uses the normal revision and
approval-invalidation path.

### Command-agent bridge

Optional assistants are subprocesses with a JSON-in/JSON-out contract. Requests contain only the scoped field or review bundle. Responses are recorded as suggestions and never become user decisions automatically. Provider-specific adapters belong outside the core protocol.

Both output streams are drained with fixed memory bounds while the subprocess runs. A timeout or
stream overflow terminates that invocation. Request failures are stored separately from valid
responses and appended to the event ledger.

The facilitator/composer and independent critic can be separate commands. A composer may return a
complete `next_document`, containing either another clarification form or a staged initialization
package. The proposal remains outside canonical state until the user applies it against the exact
revision for which it was generated.

For a ready long-horizon initialization, the composer also emits an acyclic workflow graph. It
references staged artifacts and pinned harness capabilities instead of embedding executable
content. An independent critic reviews the complete proposed state through the existing distinct
command route.

### Compiler

Compilation is deterministic and permitted only after structural validation, semantic readiness,
and approval of the exact canonical document digest. It first claims the approved revision as
`compiling`, stages generic handoff files and any typed initialization artifacts inside the run
directory, then publishes the result before making the run terminal. Resume and result consumption
finalize a complete interrupted transaction or discard its partial bundle and restore `approved`.
A resume that reaches `compiled` emits the verified completion directly without reopening a canvas.
Compilation never modifies the caller's project automatically.

A graph-backed compilation additionally emits `workflow.json` and
`EXECUTION_CONTRACT.md`. The verifier deterministically re-derives compiled Markdown,
initialization payloads, graph resources, and the execution contract from the approved document;
changing a derived file and merely updating the mutable manifest is therefore rejected.
The local run directory is the trust boundary; its digest manifest provides integrity consistency,
not an external signature or authenticity root.

## Run layout

```text
.formalprompt/runs/<run-id>/
  document.json
  state.json
  events.jsonl
  requests/
  responses/
  failures/
  artifacts/
    specification.json
    SPECIFICATION.md
    EXECUTION_BRIEF.md
    EXECUTION_CONTRACT.md
    workflow.json
    approval.json
    manifest.json
    initialization/
      <approved initialization artifacts>
```

## State machine

```text
DRAFT -> USER_EDITING -> FACILITATOR_REVIEW
  ^                          |
  |------ NEEDS_CLARIFICATION
                             v
                    INDEPENDENT_REVIEW
                             |
  USER_EDITING <- NEEDS_RESOLUTION
                             v
                       USER_APPROVAL
                             v
                         COMPILED
                             v
                        HANDED_OFF
                             v
                          CLOSED
```

The implementation uses `DRAFT -> USER_EDITING -> USER_APPROVAL -> COMPILING -> COMPILED` for
durable mutations. Facilitator, composition, and independent-review responses can propose a
revision-bound transition back to `USER_EDITING`; only a user action applies that proposal.
Canvases may require an independent-review gate: only a critic's `ready` response with no proposed
replacement passes the current revision, and every subsequent edit invalidates the pass.

## Security invariants

- Bind to `127.0.0.1` unless the user explicitly requests another interface.
- Protect every state API with an unguessable per-run bearer token.
- Put the initial token in the URL fragment so it is not sent in HTTP requests or logs; the UI stores it in session storage and removes the fragment.
- Reject cross-origin state changes and do not enable permissive CORS.
- Treat all document strings and assistant output as data; render with text nodes, never `innerHTML`.
- Evaluate agent-authored field patterns only with bounded RE2; never forward them to a browser
  regular-expression engine.
- Do not accept document-supplied scripts, event handlers, URLs, or filesystem paths.
- Restrict writes to the run directory until a distinct, explicit export operation exists.
- Keep model credentials in the host environment and out of documents, events, and browser responses.
- Suggestions do not alter canonical values without a user action.
- Compilation requires an approval record tied to the current revision and document digest.
- Authenticated OpenAI-compatible requests require HTTPS except on loopback and never follow HTTP
  redirects.

## Context isolation

The caller supplies the initial document and eventually receives a compact result object.
Facilitator transcripts, review deliberation, browser events, and intermediate revisions remain in
the run directory and external agent processes. A handoff contains the final execution brief,
artifact manifest, unresolved-item count, approval revision, approved document digest, and
paths—not the full transcript.

The approved workflow, Git history, and harness session log remain the sources of truth for intent,
changes, and execution. A material local intervention adds only a sparse correlation marker to the
existing run event stream. It must never rewrite the approved graph, duplicate those histories, or
make a causal or upstream-policy judgment from the project-execution context.
