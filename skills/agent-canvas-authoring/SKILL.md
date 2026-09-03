---
name: agent-canvas-authoring
description: Author secure Agent Canvas documents and launch them.
license: MIT
metadata:
  hermes:
    tags: [Agent Canvas, Specifications, CLI, Forms]
    related_skills: []
---

# Agent Canvas Authoring Skill

Construct a declarative canvas from the caller's current understanding, validate it, and open FormalPrompt for user review. The canvas is a typed communication boundary, not a place to inject scripts or arbitrary HTML.

## When to Use

- A request has multiple consequential specifications or assumptions.
- The user would benefit from inspecting the agent's interpretation spatially rather than through serial questions.
- Clarification should happen outside the primary execution context.
- Do not use for a single low-stakes question that can be answered directly.

## Prerequisites

- FormalPrompt is installed and `formalprompt --help` succeeds through the `terminal` tool.
- Read `docs/protocol.md` before creating a document without a template.
- Use a normal browser on graphical desktops and install Carbonyl separately for terminal-only rendering.

## Quick Reference

```text
formalprompt template minimal canvas.json
formalprompt template software-project canvas.json
formalprompt validate canvas.json --json
formalprompt open canvas.json --renderer auto --json
formalprompt open canvas.json --renderer browser --json
formalprompt open canvas.json --renderer carbonyl --json
formalprompt open canvas.json --renderer none --json
formalprompt open canvas.json --assistant-command <composer> --reviewer-command <critic> --json
formalprompt result <run-directory> --json
```

## Procedure

1. Create the closest template with `terminal(command="formalprompt template software-project canvas.json")`, or author a document against `docs/protocol.md`. Confirm the file exists.
2. Fill values only from the request and available evidence. Mark direct statements `explicit`; defensible interpretations `inferred`; recommendations `proposed`; and unknowns `unresolved`. Confirm every field carries provenance, review status, and importance.
3. Put only execution-blocking unknowns at `importance: blocker`. Give each inference or proposal a concise rationale. Confirm color is not required to understand any state.
4. Enable field assistance only where options or tradeoffs are genuinely useful. The assistance prompt must constrain the facilitator rather than invite unrelated scope.
5. Run `terminal(command="formalprompt validate canvas.json --json")`. Exit code 0 means ready for approval; exit code 2 means structurally valid with issues the canvas is expected to resolve; exit code 1 means fix the document before continuing.
6. Start the canvas with `terminal(command="formalprompt open canvas.json --renderer auto --json", background=true, notify=true)`. Read the ready event and give the user the URL only if no renderer opened automatically. Confirm the event contains a run ID and run directory.
7. If an ephemeral composer is configured, let the user request and explicitly apply focused follow-up canvases or a typed initialization package. A separate reviewer command can challenge the resulting canonical document before approval. Never treat an agent proposal as applied merely because it was returned.
8. Wait for the process completion notification or inspect it with the `process` tool. A completed event and `result.json` prove compilation; a stopped process without them does not.

## Renderer Selection

- `auto`: graphical browser on a desktop; Carbonyl over SSH/headless Linux when installed; URL-only otherwise.
- `browser`: explicitly use the system graphical browser.
- `carbonyl`: explicitly require the `carbonyl` executable.
- `none`: serve and print the URL without launching a browser; useful for remote forwarding and tests.

## Pitfalls

- Do not generate JavaScript, event handlers, URLs, or filesystem paths in a canvas document; the v1 schema intentionally rejects them.
- Do not mark an assumption `explicit` merely because it seems obvious.
- Do not stream browser events, facilitator transcripts, or `events.jsonl` into the primary agent context.
- Carbonyl is a terminal Chromium renderer, but native availability varies by platform. On native Windows, prefer the graphical renderer or use Carbonyl through a supported Linux environment.
- An `open` command normally blocks until compilation. Run it as a managed background process when the caller must continue working.

## Verification

- `formalprompt validate` reports `valid: true` before launch.
- The ready event names the expected renderer and run directory.
- The user can identify assumptions and blockers without relying on color.
- Completion produces `result.json` and an `artifacts/manifest.json` tied to the approved revision.
