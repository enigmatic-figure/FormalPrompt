# Knowledge: Repository conventions

## Purpose
Give implementation nodes a single, auditable place that names the repository''s actual structure, so agents do not discover it by expensive search.

## Contents to tailor
- **Layout**: where implementation lives (`src/agent/` vs `src/formalprompt/`), where tests live, where docs/reports belong.
- **Tooling**: package manager (`uv`), test runner (`pytest -q`), linter (`ruff check` / `ruff format --check`), compiler (`uv build`), browser check (`node --check src/static/app.js`).
- **Branching**: base branch (`main`), feature isolation preference, tag convention (`formalprompt/true-initialization` is reserved).
- **Write scopes**: canonical relative globs for typical node kinds (e.g., `src/**` for feature work, `tests/**` for tests, `docs/**` for docs).
- **Evidence conventions**: where to write ephemeral logs, how to name report artifacts.

## Usage
Bind this file as a `knowledge` resource (`knowledge-base-plan`) and list it in an `agent` or `operation` node''s `context_resources` when that node benefits from knowing conventions up front. Keep it inside `write_scope` of a planning node if it must be updated.
