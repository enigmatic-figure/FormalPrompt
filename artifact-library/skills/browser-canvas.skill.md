# Skill: Browser-canvas presentation (semantic, sandboxed)

## Purpose
Render a FormalPrompt canvas (or other declarative UI) as semantic HTML that feels like a native application without executing agent-supplied code.

## When to apply
A node needs a planner, configurator, or reviewer experience that a CLI conversation cannot provide.

## Method
1. Use canonical state as source of truth — render `CanvasDocument` fields, artifacts, and workflow nodes from the broker, never from a stale cache.
2. Build semantic HTML: form controls, tabs, badges for `provenance`/`review_status`, and a DAG canvas with `svg` edges. Use `textContent`, never `innerHTML`. Treat every string as data.
3. Keep agent-authored patterns off the browser (RE2 server-side only). Enforce CSP, auth, and scope boundaries from the broker.
4. Make every mutation revision-bound: `expected_revision` → atomic replace → event. Invalidate approval on edit.

## Security
- No scripts, event handlers, or URLs from documents.
- No filesystem writes outside the run directory.
- Token in fragment, stored in `sessionStorage`, cleared from history.

## Evidence
- Static HTML passes CSP header checks, `innerHTML` absent, `textContent` present, `sessionStorage` token handling verified.
