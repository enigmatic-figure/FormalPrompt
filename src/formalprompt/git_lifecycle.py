from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from formalprompt.artifacts import verify_compiled_run

DEFAULT_BASELINE_TAG = "formalprompt/true-initialization"
SENSITIVE_NAMES = {"AGENTS.md"}
SENSITIVE_PREFIXES = (
    ".agents/",
    "assets/",
    "docs/",
    "prompts/",
    "skills/",
    "stills/",
    "templates/",
)


class GitLifecycleError(RuntimeError):
    pass


def create_checkpoint(
    repository: Path,
    *,
    tag: str = DEFAULT_BASELINE_TAG,
    run_directory: Path | None = None,
    push: bool = False,
) -> dict[str, Any]:
    repo = _repository_root(repository)
    _require_clean(repo)
    _git(repo, "check-ref-format", f"refs/tags/{tag}")
    existing = _git(repo, "tag", "--list", tag)
    if existing:
        raise GitLifecycleError(f"Checkpoint tag already exists: {tag}")

    run_metadata: dict[str, Any] | None = None
    if run_directory is not None:
        result, _ = verify_compiled_run(run_directory)
        run_metadata = {
            "run_id": result["run_id"],
            "revision": result["revision"],
            "handoff": result["handoff"],
        }

    commit = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "branch", "--show-current")
    if not branch:
        raise GitLifecycleError("True Initialization cannot be tagged from a detached HEAD")
    remote = _git(repo, "remote", "get-url", "origin", allow_failure=True) or None
    if push and remote is None:
        raise GitLifecycleError("Cannot push checkpoint without an origin remote")
    checkpoint = {
        "contract": "formalprompt-initialization-checkpoint/v1",
        "tag": tag,
        "commit": commit,
        "branch": branch,
        "remote": remote,
        "created_at": _now(),
        "run": run_metadata,
    }
    message = json.dumps(checkpoint, ensure_ascii=False, separators=(",", ":"))
    _git(repo, "tag", "--annotate", tag, commit, "--message", message)
    if push:
        try:
            _git(repo, "push", "origin", branch)
            _git(repo, "push", "origin", f"refs/tags/{tag}")
        except GitLifecycleError:
            _git(repo, "tag", "--delete", tag, allow_failure=True)
            raise
    return checkpoint


def create_retrospective(
    repository: Path,
    *,
    baseline: str = DEFAULT_BASELINE_TAG,
    output: Path,
    patch_output: Path,
    force: bool = False,
) -> dict[str, Any]:
    repo = _repository_root(repository)
    if not force:
        for path in (output, patch_output):
            if path.exists():
                raise GitLifecycleError(f"Refusing to replace existing retrospective file: {path}")
    baseline_commit = _git(repo, "rev-parse", f"{baseline}^{{commit}}")
    head = _git(repo, "rev-parse", "HEAD")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline_commit, head],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if ancestor.returncode != 0:
        raise GitLifecycleError("True Initialization checkpoint is not an ancestor of HEAD")

    name_status = _git(repo, "diff", "--name-status", "--find-renames", baseline_commit, head)
    stat = _git(repo, "diff", "--stat", baseline_commit, head)
    commits = _git(repo, "log", "--oneline", f"{baseline_commit}..{head}")
    patch = _git(repo, "diff", "--binary", baseline_commit, head, strip=False)
    changed = _parse_name_status(name_status)
    sensitive = [item for item in changed if _is_initialization_sensitive(item["path"])]
    report = _retrospective_markdown(
        baseline=baseline,
        baseline_commit=baseline_commit,
        head=head,
        stat=stat,
        commits=commits,
        changed=changed,
        sensitive=sensitive,
        patch_output=patch_output,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    patch_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8", newline="\n")
    patch_output.write_text(patch + ("" if patch.endswith("\n") else "\n"), encoding="utf-8")
    return {
        "contract": "formalprompt-initialization-retrospective/v1",
        "baseline": baseline,
        "baseline_commit": baseline_commit,
        "head": head,
        "changed_files": len(changed),
        "initialization_sensitive_files": len(sensitive),
        "report": str(output.resolve()),
        "patch": str(patch_output.resolve()),
    }


def _repository_root(repository: Path) -> Path:
    candidate = repository.resolve()
    root = _git(candidate, "rev-parse", "--show-toplevel", allow_failure=True)
    if not root:
        raise GitLifecycleError(f"Not a Git repository: {candidate}")
    return Path(root).resolve()


def _require_clean(repo: Path) -> None:
    if _git(repo, "status", "--porcelain"):
        raise GitLifecycleError("True Initialization requires a clean committed working tree")


def _git(repo: Path, *arguments: str, allow_failure: bool = False, strip: bool = True) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise GitLifecycleError("Git could not be executed") from exc
    if completed.returncode != 0:
        if allow_failure:
            return ""
        detail = (completed.stderr or completed.stdout).strip()
        raise GitLifecycleError(f"Git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip() if strip else completed.stdout


def _parse_name_status(value: str) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for line in value.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]
        changes.append({"status": status, "path": path})
    return changes


def _is_initialization_sensitive(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        normalized in SENSITIVE_NAMES
        or Path(normalized).name in SENSITIVE_NAMES
        or normalized.startswith(SENSITIVE_PREFIXES)
        or normalized.casefold().endswith(".md")
    )


def _retrospective_markdown(
    *,
    baseline: str,
    baseline_commit: str,
    head: str,
    stat: str,
    commits: str,
    changed: list[dict[str, str]],
    sensitive: list[dict[str, str]],
    patch_output: Path,
) -> str:
    lines = [
        "# Initialization Retrospective",
        "",
        f"- Baseline tag: `{baseline}`",
        f"- True Initialization commit: `{baseline_commit}`",
        f"- Completion commit: `{head}`",
        f"- Full diff: `{patch_output}`",
        "",
        "## Change summary",
        "",
        "```text",
        stat or "No committed changes after True Initialization.",
        "```",
        "",
        "## Initialization-sensitive changes",
        "",
    ]
    if sensitive:
        lines.extend(f"- `{item['status']}` `{item['path']}`" for item in sensitive)
    else:
        lines.append("No prompt, skill, template, documentation, or governance files changed.")
    lines.extend(["", "## Commits after True Initialization", "", "```text"])
    lines.append(commits or "No commits after the checkpoint.")
    lines.extend(["```", "", "## All changed files", ""])
    if changed:
        lines.extend(f"- `{item['status']}` `{item['path']}`" for item in changed)
    else:
        lines.append("No committed file changes.")
    lines.extend(
        [
            "",
            "## Scope",
            "",
            "This report is a mechanically derived Git comparison. It does not diagnose causes, "
            "attribute responsibility, or recommend reusable-system changes. Correlate it with the "
            "FormalPrompt intervention audit index during a separate high-context review.",
            "",
        ]
    )
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(UTC).isoformat()
