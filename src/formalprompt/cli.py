from __future__ import annotations

import json
import os
import secrets
import shlex
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from formalprompt.artifacts import ArtifactBundleError, materialize_initialization
from formalprompt.assistant import CommandAssistant
from formalprompt.compiler import load_verified_result, recover_interrupted_compilation
from formalprompt.git_lifecycle import (
    DEFAULT_BASELINE_TAG,
    GitLifecycleError,
    create_checkpoint,
    create_retrospective,
)
from formalprompt.interventions import (
    InterventionAuditIndex,
    InterventionError,
    InterventionMarker,
    collect_audit_index,
    record_intervention,
)
from formalprompt.launchers import LauncherUnavailable
from formalprompt.models import CanvasDocument
from formalprompt.runtime import CanvasRuntime
from formalprompt.store import RunStore
from formalprompt.validation import independent_review_issue, validate_document

app = typer.Typer(
    name="formalprompt",
    help="Open a browser canvas for externalized agent deliberation.",
    no_args_is_help=True,
)
TEMPLATE_DIRECTORY = Path(__file__).parent / "templates"
TEMPLATES = {
    "formalprompt-self-hosting": TEMPLATE_DIRECTORY / "formalprompt-self-hosting.json",
    "minimal": TEMPLATE_DIRECTORY / "minimal.json",
    "software-project": TEMPLATE_DIRECTORY / "software-project.json",
    "workflow-project": TEMPLATE_DIRECTORY / "workflow-project.json",
}
SCHEMA_MODELS = {
    "canvas": CanvasDocument,
    "intervention": InterventionMarker,
    "audit-index": InterventionAuditIndex,
}


@app.command("validate")
def validate_command(
    document: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    try:
        model = CanvasDocument.model_validate_json(document.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        payload = {"valid": False, "errors": _validation_errors(exc)}
        _emit(payload, as_json)
        raise typer.Exit(1) from None
    issues = validate_document(model)
    if model.completion.require_independent_review:
        issues.append(independent_review_issue())
    payload = {
        "valid": True,
        "ready": not any(issue.severity == "error" for issue in issues),
        "issues": [issue.model_dump(mode="json") for issue in issues],
    }
    _emit(payload, as_json)
    if not payload["ready"]:
        raise typer.Exit(2)


@app.command("template")
def template_command(
    name: Annotated[str, typer.Argument(help="Template name.")],
    output: Annotated[Path, typer.Argument(dir_okay=False)],
    force: Annotated[bool, typer.Option("--force", help="Replace an existing file.")] = False,
) -> None:
    source = TEMPLATES.get(name)
    if source is None:
        choices = ", ".join(sorted(TEMPLATES))
        raise typer.BadParameter(f"Unknown template {name!r}. Available: {choices}")
    if output.exists() and not force:
        raise typer.BadParameter(f"Output already exists: {output}")
    content = source.read_text(encoding="utf-8")
    CanvasDocument.model_validate_json(content)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    typer.echo(str(output.resolve()))


@app.command("schema")
def schema_command(
    output: Annotated[Path, typer.Argument(dir_okay=False)],
    force: Annotated[bool, typer.Option("--force", help="Replace an existing file.")] = False,
    contract: Annotated[
        str,
        typer.Option(
            "--contract",
            help="Schema contract: canvas, intervention, or audit-index.",
        ),
    ] = "canvas",
) -> None:
    if output.exists() and not force:
        raise typer.BadParameter(f"Output already exists: {output}")
    model = SCHEMA_MODELS.get(contract)
    if model is None:
        choices = ", ".join(sorted(SCHEMA_MODELS))
        raise typer.BadParameter(f"Unknown schema contract {contract!r}. Available: {choices}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    typer.echo(str(output.resolve()))


@app.command("open")
def open_command(
    document: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    runs_dir: Annotated[
        Path | None,
        typer.Option("--runs-dir", help="Run storage root; defaults beside the document."),
    ] = None,
    renderer: Annotated[
        str, typer.Option("--renderer", help="auto, browser, carbonyl, or none.")
    ] = "auto",
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=0, max=65535)] = 0,
    assistant_command: Annotated[
        str | None,
        typer.Option("--assistant-command", help="JSON-in/JSON-out facilitator command."),
    ] = None,
    reviewer_command: Annotated[
        str | None,
        typer.Option(
            "--reviewer-command",
            help="JSON-in/JSON-out independent critic command; defaults to the assistant.",
        ),
    ] = None,
    assistant_timeout: Annotated[
        int,
        typer.Option("--assistant-timeout", min=1, help="Assistant command timeout in seconds."),
    ] = 600,
    reviewer_timeout: Annotated[
        int,
        typer.Option("--reviewer-timeout", min=1, help="Reviewer command timeout in seconds."),
    ] = 600,
    allow_remote: Annotated[
        bool, typer.Option("--allow-remote", help="Permit a non-loopback bind address.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON Lines lifecycle events.")
    ] = False,
) -> None:
    model = _read_document(document)
    root = runs_dir or document.parent / ".formalprompt" / "runs"
    store = RunStore.create(root, model)
    _serve_store(
        store,
        renderer=renderer,
        host=host,
        port=port,
        assistant_command=assistant_command,
        reviewer_command=reviewer_command,
        assistant_timeout=assistant_timeout,
        reviewer_timeout=reviewer_timeout,
        allow_remote=allow_remote,
        as_json=as_json,
    )


@app.command("resume")
def resume_command(
    run_directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    renderer: Annotated[str, typer.Option("--renderer")] = "auto",
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=0, max=65535)] = 0,
    assistant_command: Annotated[str | None, typer.Option("--assistant-command")] = None,
    reviewer_command: Annotated[str | None, typer.Option("--reviewer-command")] = None,
    assistant_timeout: Annotated[int, typer.Option("--assistant-timeout", min=1)] = 600,
    reviewer_timeout: Annotated[int, typer.Option("--reviewer-timeout", min=1)] = 600,
    allow_remote: Annotated[bool, typer.Option("--allow-remote")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    store = RunStore(run_directory.resolve())
    store.read_document()
    store.read_state()
    recover_interrupted_compilation(store)
    if store.read_state().get("status") == "compiled":
        try:
            _emit_lifecycle(_completed_payload(store), as_json)
        except (ArtifactBundleError, OSError, ValueError) as exc:
            _emit_lifecycle(
                {
                    "contract": "agent-canvas-session/v1",
                    "event": "error",
                    "run_id": store.run_id,
                    "message": f"Compiled result verification failed: {exc}",
                },
                as_json,
            )
            raise typer.Exit(1) from None
        return
    _serve_store(
        store,
        renderer=renderer,
        host=host,
        port=port,
        assistant_command=assistant_command,
        reviewer_command=reviewer_command,
        assistant_timeout=assistant_timeout,
        reviewer_timeout=reviewer_timeout,
        allow_remote=allow_remote,
        as_json=as_json,
    )


@app.command("result")
def result_command(
    run_directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    store = RunStore(run_directory.resolve())
    try:
        payload = load_verified_result(store)
    except (ArtifactBundleError, OSError, ValueError) as exc:
        typer.echo(f"The run has no verified compiled result: {exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo(
        json.dumps(payload, ensure_ascii=False) if as_json else json.dumps(payload, indent=2)
    )


@app.command("materialize")
def materialize_command(
    run_directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    destination: Annotated[Path, typer.Argument(help="Project directory to receive staged files.")],
    force: Annotated[bool, typer.Option("--force", help="Replace existing project files.")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        written = materialize_initialization(run_directory, destination, force=force)
    except ArtifactBundleError as exc:
        typer.echo(f"Initialization materialization failed: {exc}", err=True)
        raise typer.Exit(1) from None
    payload = {
        "contract": "formalprompt-materialization/v1",
        "destination": str(destination.resolve()),
        "files": [str(path.resolve()) for path in written],
    }
    _emit_object(payload, as_json)


@app.command("checkpoint")
def checkpoint_command(
    repository: Annotated[Path, typer.Argument(exists=True, file_okay=False)] = Path("."),
    tag: Annotated[str, typer.Option("--tag", help="Immutable True Initialization tag.")] = (
        DEFAULT_BASELINE_TAG
    ),
    run_directory: Annotated[
        Path | None,
        typer.Option(
            "--run-directory",
            exists=True,
            file_okay=False,
            help="Optional compiled run to bind to the checkpoint annotation.",
        ),
    ] = None,
    push: Annotated[
        bool, typer.Option("--push", help="Push the current branch and checkpoint tag to origin.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        payload = create_checkpoint(repository, tag=tag, run_directory=run_directory, push=push)
    except (ArtifactBundleError, GitLifecycleError) as exc:
        typer.echo(f"Initialization checkpoint failed: {exc}", err=True)
        raise typer.Exit(1) from None
    _emit_object(payload, as_json)


@app.command("intervene")
def intervene_command(
    run_directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    graph_node: Annotated[str, typer.Option("--node", help="Active approved workflow node.")],
    repository: Annotated[
        Path,
        typer.Option("--project", exists=True, file_okay=False, help="Project Git repository."),
    ] = Path("."),
    session_event: Annotated[
        str | None,
        typer.Option(
            "--session-event",
            help="Existing session-log correlation ID; otherwise one is generated.",
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        payload = record_intervention(
            run_directory,
            graph_node=graph_node,
            repository=repository,
            session_event=session_event or os.environ.get("FORMALPROMPT_SESSION_EVENT"),
        )
    except InterventionError as exc:
        typer.echo(f"Intervention flag failed: {exc}", err=True)
        raise typer.Exit(1) from None
    _emit_object(payload, as_json)


@app.command("audit-index")
def audit_index_command(
    run_directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    repository: Annotated[
        Path,
        typer.Option("--project", exists=True, file_okay=False, help="Project Git repository."),
    ] = Path("."),
    session_log: Annotated[
        Path | None,
        typer.Option("--session-log", exists=True, dir_okay=False, readable=True),
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False)] = None,
    window_lines: Annotated[
        int,
        typer.Option("--window-lines", min=0, help="Line radius around each session anchor."),
    ] = 12,
    force: Annotated[bool, typer.Option("--force")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        payload = collect_audit_index(
            run_directory,
            repository=repository,
            session_log=session_log,
            output=output,
            window_lines=window_lines,
            force=force,
        )
    except InterventionError as exc:
        typer.echo(f"Intervention audit index failed: {exc}", err=True)
        raise typer.Exit(1) from None
    _emit_object(payload, as_json)


@app.command("retrospective")
def retrospective_command(
    repository: Annotated[Path, typer.Argument(exists=True, file_okay=False)] = Path("."),
    baseline: Annotated[str, typer.Option("--baseline")] = DEFAULT_BASELINE_TAG,
    output: Annotated[Path, typer.Option("--output")] = Path("INITIALIZATION_RETROSPECTIVE.md"),
    patch_output: Annotated[Path, typer.Option("--patch-output")] = Path(
        "INITIALIZATION_RETROSPECTIVE.patch"
    ),
    force: Annotated[bool, typer.Option("--force")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    root = repository.resolve()
    resolved_output = output if output.is_absolute() else root / output
    resolved_patch = patch_output if patch_output.is_absolute() else root / patch_output
    try:
        payload = create_retrospective(
            repository,
            baseline=baseline,
            output=resolved_output,
            patch_output=resolved_patch,
            force=force,
        )
    except GitLifecycleError as exc:
        typer.echo(f"Initialization retrospective failed: {exc}", err=True)
        raise typer.Exit(1) from None
    _emit_object(payload, as_json)


def _serve_store(
    store: RunStore,
    *,
    renderer: str,
    host: str,
    port: int,
    assistant_command: str | None,
    reviewer_command: str | None,
    assistant_timeout: int,
    reviewer_timeout: int,
    allow_remote: bool,
    as_json: bool,
) -> None:
    allowed_renderers = {"auto", "browser", "carbonyl", "none"}
    if renderer not in allowed_renderers:
        choices = ", ".join(sorted(allowed_renderers))
        raise typer.BadParameter(f"Unknown renderer {renderer!r}; choose {choices}")
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_remote:
        raise typer.BadParameter("Non-loopback binding requires --allow-remote")
    assistant = None
    if assistant_command:
        command = shlex.split(assistant_command, posix=os.name != "nt")
        assistant = CommandAssistant(command, timeout_seconds=assistant_timeout)
    reviewer = None
    if reviewer_command:
        command = shlex.split(reviewer_command, posix=os.name != "nt")
        reviewer = CommandAssistant(command, timeout_seconds=reviewer_timeout)
    token = secrets.token_urlsafe(32)
    runtime = CanvasRuntime(
        store,
        token=token,
        host=host,
        port=port,
        renderer=renderer,
        assistant=assistant,
        reviewer=reviewer,
    )
    try:
        runtime.start()
        if not runtime.wait_until_ready():
            raise RuntimeError("Canvas server failed to become ready")
        try:
            runtime.open_renderer()
        except LauncherUnavailable as exc:
            runtime.renderer = "none"
            _emit_lifecycle(
                {
                    "contract": "agent-canvas-session/v1",
                    "event": "renderer-fallback",
                    "run_id": store.run_id,
                    "renderer": "none",
                    "message": str(exc),
                },
                as_json,
            )
        ready = {
            "contract": "agent-canvas-session/v1",
            "event": "ready",
            "run_id": store.run_id,
            "run_directory": str(store.path.resolve()),
            "renderer": runtime.renderer,
            "url": runtime.canvas_url,
        }
        _emit_lifecycle(ready, as_json)
        runtime.wait()
    except KeyboardInterrupt:
        if not as_json:
            typer.echo("Canvas stopped before compilation.")
    except RuntimeError as exc:
        _emit_lifecycle(
            {
                "contract": "agent-canvas-session/v1",
                "event": "error",
                "run_id": store.run_id,
                "message": str(exc),
            },
            as_json,
        )
        raise typer.Exit(1) from None
    finally:
        runtime.stop()
    status = store.read_state().get("status")
    if status in {"compiling", "compiled"}:
        try:
            completed = _completed_payload(store)
        except (ArtifactBundleError, OSError, ValueError) as exc:
            _emit_lifecycle(
                {
                    "contract": "agent-canvas-session/v1",
                    "event": "error",
                    "run_id": store.run_id,
                    "message": f"Compiled result verification failed: {exc}",
                },
                as_json,
            )
            raise typer.Exit(1) from None
        _emit_lifecycle(completed, as_json)


def _completed_payload(store: RunStore) -> dict:
    result = load_verified_result(store)
    return {"event": "completed", "run_directory": str(store.path.resolve()), **result}


def _read_document(path: Path) -> CanvasDocument:
    try:
        return CanvasDocument.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        typer.echo(f"Invalid canvas document: {exc}", err=True)
        raise typer.Exit(1) from None


def _emit_lifecycle(payload: dict, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    event = payload.get("event")
    if event == "ready":
        typer.echo(f"Canvas ready: {payload['url']}")
        typer.echo(f"Run directory: {payload['run_directory']}")
        typer.echo(f"Renderer: {payload['renderer']}")
    elif event == "renderer-fallback":
        typer.echo(f"Renderer unavailable; continuing in URL-only mode: {payload['message']}")
    elif event == "error":
        typer.echo(f"Canvas failed: {payload['message']}", err=True)
    else:
        typer.echo(f"Canvas completed. Handoff: {payload.get('handoff')}")


def _validation_errors(error: Exception) -> list[dict]:
    if isinstance(error, ValidationError):
        return [
            {
                "location": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors()
        ]
    return [{"location": "document", "message": str(error), "type": "value_error"}]


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    if payload.get("valid") and payload.get("ready"):
        typer.echo("Document is structurally valid and ready for approval.")
    elif payload.get("valid"):
        typer.echo("Document is structurally valid but has semantic issues.")
        for issue in payload.get("issues", []):
            typer.echo(f"- {issue['code']}: {issue['message']}")
    else:
        typer.echo("Document is invalid.", err=True)
        for error in payload.get("errors", []):
            typer.echo(f"- {error['location']}: {error['message']}", err=True)


def _emit_object(payload: dict, as_json: bool) -> None:
    typer.echo(
        json.dumps(payload, ensure_ascii=False)
        if as_json
        else json.dumps(payload, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    app()
