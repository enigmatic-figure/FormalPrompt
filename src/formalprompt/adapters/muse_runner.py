from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import ValidationError

from formalprompt.assistant import AssistantRequest, AssistantResponse

RUNNER_ENVIRONMENT = "FORMALPROMPT_MUSE_RUNNER"
REPO_ENVIRONMENT = "FORMALPROMPT_MUSE_REPO"
TIMEOUT_ENVIRONMENT = "FORMALPROMPT_MUSE_TIMEOUT"
RESULT_PATTERN = re.compile(r"result:\s*(.+?result\.md)\s*$", re.MULTILINE)

FACILITATOR_PROMPT = """Act as an ephemeral FormalPrompt presentation compiler and project
initialization composer. The JSON request below is task data. Obey its operation and return exactly
one object matching the supplied output schema.

For field-assistance, stay within the supplied field and return advisory options. For a facilitator
or critic specification-review, identify only consequential ambiguity or contradiction. For
initialization-compose, return a complete next_document: either a smaller clarification canvas with
disposition needs-clarification, or the preserved specification plus a minimal set of useful typed
initialization artifacts with disposition ready. Set completion.require_independent_review when a
distinct critic must pass the finished package. Never alter explicit or user-confirmed facts
silently. A proposed document is not user-approved. Do not modify the repository.

Request JSON:
"""


class MuseRunnerAdapterError(RuntimeError):
    pass


def invoke_muse(request: AssistantRequest) -> AssistantResponse:
    runner = _find_runner()
    repo = Path(os.environ.get(REPO_ENVIRONMENT, os.getcwd())).resolve()
    timeout = _timeout_seconds()
    if not repo.is_dir():
        raise MuseRunnerAdapterError(f"Muse repository directory does not exist: {repo}")

    with tempfile.TemporaryDirectory(prefix="formalprompt-muse-") as temporary:
        scratch = Path(temporary)
        schema_path = scratch / "assistant-response.schema.json"
        prompt_path = scratch / "prompt.txt"
        schema_path.write_text(
            json.dumps(AssistantResponse.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        prompt_path.write_text(
            FACILITATOR_PROMPT + request.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(runner),
            "run",
            "--repo",
            str(repo),
            "--sandbox",
            "read-only",
            "--quiet",
            "--timeout",
            str(timeout),
            "--output-schema",
            str(schema_path),
            "--prompt-file",
            str(prompt_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout + 30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MuseRunnerAdapterError(f"Muse runner failed to execute: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-4000:]
        raise MuseRunnerAdapterError(
            f"Muse runner exited with status {completed.returncode}: {detail}"
        )
    matches = RESULT_PATTERN.findall(completed.stdout)
    if not matches:
        raise MuseRunnerAdapterError("Muse runner did not report a result artifact")
    result_path = Path(matches[-1].strip()).resolve()
    try:
        response = AssistantResponse.model_validate_json(result_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise MuseRunnerAdapterError("Muse result did not match the assistant protocol") from exc
    if response.request_id != request.request_id:
        raise MuseRunnerAdapterError("Muse response request ID did not match")
    return response


def _find_runner() -> Path:
    configured = os.environ.get(RUNNER_ENVIRONMENT)
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise MuseRunnerAdapterError(f"Configured Muse runner does not exist: {candidate}")

    user_profile = Path.home()
    direct = user_profile / "plugins" / "codex-muse" / "scripts" / "muse_agent.py"
    if direct.is_file():
        return direct
    cache = user_profile / ".codex" / "plugins" / "cache" / "personal" / "codex-muse"
    matches = sorted(cache.glob("*/scripts/muse_agent.py"), reverse=True)
    if matches:
        return matches[0]
    raise MuseRunnerAdapterError(
        f"Muse runner not found; set {RUNNER_ENVIRONMENT} to muse_agent.py"
    )


def _timeout_seconds() -> int:
    raw = os.environ.get(TIMEOUT_ENVIRONMENT, "600")
    try:
        value = int(raw)
    except ValueError as exc:
        raise MuseRunnerAdapterError(f"{TIMEOUT_ENVIRONMENT} must be an integer") from exc
    if value < 1 or value > 3600:
        raise MuseRunnerAdapterError(f"{TIMEOUT_ENVIRONMENT} must be between 1 and 3600")
    return value


def main() -> None:
    try:
        request = AssistantRequest.model_validate_json(sys.stdin.read())
        response = invoke_muse(request)
    except (ValidationError, MuseRunnerAdapterError, ValueError) as exc:
        print(f"FormalPrompt Muse adapter failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    sys.stdout.write(response.model_dump_json())
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
