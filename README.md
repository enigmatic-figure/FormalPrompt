# FormalPrompt

FormalPrompt is a local browser canvas for externalized agent deliberation. A CLI agent supplies a versioned, declarative canvas document; the user reviews and edits it in a normal graphical browser or Carbonyl; deterministic validation and isolated assistant processes help converge on a specification; and a compact, auditable artifact bundle returns to the execution agent.

The project has two layers:

- **Agent Canvas** — the general local protocol, renderer, lifecycle, and command-agent bridge.
- **FormalPrompt** — the first canvas kind: a provenance-aware specification workbench and handoff compiler.

The canonical state is the canvas document. The browser, facilitator, reviewer, validators, and compiler are projections or processors of that document—not competing sources of truth.

## What works in v0.1

- Strict `agent-canvas/v1` document models and generated JSON Schema.
- Tabbed, responsive forms with six native field types.
- Visible provenance, review state, importance, rationale, and blocker treatment.
- Optimistic revisions, autosave, atomic JSON replacement, and append-only events.
- Deterministic validation with crash-safe malformed-rule handling.
- Revision-bound user approval and automatic approval invalidation after edits.
- Terminal compiled runs and an atomic `approved -> compiling -> compiled` claim.
- Staged Markdown/JSON handoffs with SHA-256 manifest and machine-readable result.
- Typed, editable initialization artifacts for primary prompts, agent definitions, skills,
  research requests, knowledge-base plans, and project plans.
- Authenticated loopback FastAPI server with restrictive browser security headers.
- Graphical-browser, Carbonyl, automatic, and URL-only launch modes.
- Field assistance plus facilitator and adversarial whole-spec review.
- User-accepted next-canvas proposals for iterative clarification or initialization composition.
- Provider-neutral JSON command bridge and an OpenAI-compatible reference adapter.
- A concrete ephemeral Muse runner adapter with schema-constrained responses.
- Separate facilitator/composer and independent-reviewer command routes.
- Optional revision-bound independent-review gating before user approval.
- Three agent skills and three starting templates, including a self-hosting canvas.
- Real headless-Chrome integration coverage for edit → validate → approve → compile.

## Install for development

FormalPrompt requires Python 3.11 or newer. This repository uses `uv`:

```text
uv sync --extra dev
uv run formalprompt --help
```

To install it as an isolated command from a checkout:

```text
uv tool install .
formalprompt --help
```

Carbonyl is optional and installed separately. See `docs/browser-renderers.md` for platform caveats.

## Quick start

Create a canvas document:

```text
uv run formalprompt template software-project canvas.json
```

Edit the generated values and provenance, then validate it:

```text
uv run formalprompt validate canvas.json --json
```

Exit code 0 means ready for approval. Exit code 2 means structurally valid with semantic issues intended for resolution in the canvas. Exit code 1 means the document is structurally invalid.

Open it:

```text
uv run formalprompt open canvas.json --renderer auto --json
```

The command emits a ready event containing the run directory and authenticated local URL. It normally stays alive until the user approves and compiles the canvas, then emits a completed event and exits. For an agent that must keep working while the user operates the canvas, launch this as a managed background process.

Resume an interrupted run:

```text
uv run formalprompt resume .formalprompt/runs/<run-id> --renderer auto --json
```

Read the final result without reopening the canvas:

```text
uv run formalprompt result .formalprompt/runs/<run-id> --json
```

## Browser modes

```text
--renderer auto       Desktop browser; Carbonyl in supported headless sessions; URL fallback
--renderer browser    Operating-system graphical browser
--renderer carbonyl   Require the carbonyl executable on PATH
--renderer none       Serve and print the URL without launching anything
```

Both browser options consume the same semantic HTML application. FormalPrompt does not generate a reduced text-only UI for Carbonyl and does not silently install browser software.

## Isolated assistant calls

Without an assistant command, field and review requests are durably queued under the run directory. To use the included OpenAI-compatible adapter, configure credentials in the environment:

```text
FORMALPROMPT_ASSISTANT_BASE_URL=https://provider.example/v1
FORMALPROMPT_ASSISTANT_MODEL=provider/model-name
FORMALPROMPT_ASSISTANT_API_KEY=<secret>
```

Then launch:

```text
uv run formalprompt open canvas.json \
  --assistant-command formalprompt-openai-assistant \
  --reviewer-command formalprompt-openai-assistant
```

Each click launches a fresh JSON-in/JSON-out command invocation. `--reviewer-command` is optional
and routes adversarial reviews to a distinct process; without it, the assistant command handles
both roles. Suggestions and complete next-canvas proposals remain advisory until the user explicitly
applies them. See `docs/assistant-adapters.md` for custom adapters and security constraints.

With the personal `codex-muse` plugin installed, use a fresh Muse agent for each interaction:

```text
FORMALPROMPT_MUSE_REPO=/path/to/project
uv run formalprompt open canvas.json \
  --assistant-command formalprompt-muse-assistant \
  --assistant-timeout 630
```

## Commands

```text
formalprompt validate <document> [--json]
formalprompt template <minimal|software-project|formalprompt-self-hosting> <output>
formalprompt schema <output>
formalprompt open <document> [--renderer ...] [--assistant-command ...] [--reviewer-command ...]
formalprompt resume <run-directory> [--renderer ...] [--assistant-command ...] [--reviewer-command ...]
formalprompt result <run-directory> [--json]
formalprompt materialize <run-directory> <project-directory> [--force]
formalprompt checkpoint [project-directory] [--run-directory ...] [--push]
formalprompt learn [project-directory] --artifact ... --problem ... --adjustment ... --recommendation ...
formalprompt retrospective [project-directory] [--baseline ...]
```

## Run artifacts

```text
.formalprompt/runs/<run-id>/
  document.json
  state.json
  events.jsonl
  result.json
  requests/
  responses/
  artifacts/
    specification.json
    SPECIFICATION.md
    EXECUTION_BRIEF.md
    approval.json
    manifest.json
    initialization/
      <agent-composed files...>
```

Initialization artifacts are part of the canonical, revision-bound canvas: the user can inspect and
edit them before approval. Compilation still writes only under the run directory. Installing generated
skills, prompts, or project files is an intentionally separate operation.

## Agent assets

- `skills/agent-canvas-authoring/SKILL.md` — construct, validate, and launch canvases.
- `skills/formalprompt-facilitation/SKILL.md` — operate behind the isolated JSON bridge.
- `skills/formalprompt-handoff/SKILL.md` — consume compact results without importing deliberation.
- `skills/formalprompt-initialization-lifecycle/SKILL.md` — preserve True Initialization, record
  corrections, and compare completion with the reviewed baseline.
- `schemas/agent-canvas-v1.schema.json` — generated protocol schema.
- `examples/formalprompt-project.json` — this project expressed in its own canvas.

## Security model

- Loopback binding by default; non-loopback requires `--allow-remote`.
- Unguessable bearer token delivered in the URL fragment and cleared after bootstrap.
- No permissive CORS, framing, external scripts, or agent-supplied executable browser code.
- All document and assistant strings render as text.
- Assistant commands run without a shell and receive scoped JSON.
- Model credentials remain in the host environment.
- Assistant output cannot mutate canonical state automatically.
- Compilation requires approval of the exact current revision.

This is a local preflight tool, not a multi-user network service. `--allow-remote` changes only the bind safeguard; production remote authentication and TLS are out of scope for v0.1.

## Development and verification

```text
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
node --check src/formalprompt/static/app.js
uv build
```

The Chrome integration test runs automatically when Chrome-family browser and Node executables are available; otherwise it reports a skip. A true Carbonyl rendering smoke test needs a supported OS, installed Carbonyl, and an interactive TTY.

## Current limits

- Only `formalprompt/specification` canvases are accepted; the envelope is designed for more canvas kinds later.
- External queue consumers do not yet trigger automatic response pickup in an already-open UI.
- The reference adapter uses chat completions; provider-specific agent/session APIs require custom adapters.
- Run state is file-backed and single-broker, not a concurrent multi-user database.
- Arbitrary Muse-authored presentation code is deliberately deferred to a separately sandboxed canvas kind.
- The core exposes the ephemeral composer/reviewer process boundaries but does not hard-code a particular
  Muse or ChatGPT transport; adapters own provider authentication, process lifecycle, and model selection.

See `docs/protocol.md`, `docs/architecture.md`, `docs/browser-renderers.md`, and `docs/assistant-adapters.md` for normative details.
See `docs/initialization-lifecycle.md` for private review publication, checkpointing, and the
post-execution learning loop.
