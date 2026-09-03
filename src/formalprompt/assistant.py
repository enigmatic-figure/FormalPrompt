from __future__ import annotations

import json
import subprocess
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from formalprompt.models import CanvasDocument


class AssistantProtocolError(RuntimeError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssistantRequest(StrictModel):
    contract: Literal["agent-canvas-assistant/v1"]
    request_id: str = Field(min_length=1)
    operation: Literal["field-assistance", "specification-review", "initialization-compose"]
    context: dict[str, Any]


class Suggestion(StrictModel):
    value: Any
    label: str = Field(min_length=1)
    implications: str = ""


class AssistantResponse(StrictModel):
    contract: Literal["agent-canvas-assistant/v1"]
    request_id: str = Field(min_length=1)
    summary: str
    suggestions: list[Suggestion] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    disposition: Literal["advisory", "needs-clarification", "ready"] = "advisory"
    next_document: CanvasDocument | None = None


class AssistantBackend(Protocol):
    def invoke(self, request: dict[str, Any] | AssistantRequest) -> AssistantResponse: ...


class CommandAssistant:
    def __init__(
        self,
        command: list[str],
        *,
        timeout_seconds: float = 120,
        maximum_output_bytes: int = 1_000_000,
    ):
        if not command:
            raise ValueError("Assistant command cannot be empty")
        self.command = list(command)
        self.timeout_seconds = timeout_seconds
        self.maximum_output_bytes = maximum_output_bytes

    def invoke(self, request: dict[str, Any] | AssistantRequest) -> AssistantResponse:
        envelope = (
            request
            if isinstance(request, AssistantRequest)
            else AssistantRequest.model_validate(request)
        )
        try:
            completed = subprocess.run(
                self.command,
                input=envelope.model_dump_json(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AssistantProtocolError(f"Assistant command failed to run: {exc}") from exc
        if completed.returncode != 0:
            raise AssistantProtocolError(
                f"Assistant command exited with status {completed.returncode}"
            )
        if len(completed.stdout.encode("utf-8")) > self.maximum_output_bytes:
            raise AssistantProtocolError("Assistant response exceeded the configured size limit")
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AssistantProtocolError("Assistant did not return valid JSON") from exc
        try:
            response = AssistantResponse.model_validate(raw)
        except ValidationError as exc:
            raise AssistantProtocolError("Assistant response did not match the protocol") from exc
        if response.request_id != envelope.request_id:
            raise AssistantProtocolError("Assistant response request ID did not match")
        return response
