from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from formalprompt.assistant import AssistantBackend, AssistantResponse
from formalprompt.integrity import document_sha256
from formalprompt.models import CanvasDocument
from formalprompt.validation import (
    ValidationIssue,
    independent_review_issue,
    validate_document,
    validate_field_candidate,
)

PROPOSAL_DEFINITION_ERROR_CODES = {
    "duplicate-tab-id",
    "duplicate-section-id",
    "duplicate-field-id",
    "duplicate-artifact-id",
    "duplicate-artifact-path",
    "duplicate-option",
    "missing-options",
    "invalid-pattern",
    "unsafe-pattern",
    "invalid-length-range",
    "invalid-number-range",
    "invalid-type",
    "invalid-option",
    "unsafe-artifact-path",
    "unknown-primary-artifact",
}


class RevisionConflict(Exception):
    pass


class ValidationFailed(Exception):
    def __init__(self, issues: list[ValidationIssue]):
        super().__init__("Document is not ready for approval")
        self.issues = issues


class RunStore:
    def __init__(self, path: Path):
        self.path = path
        self.run_id = path.name
        self._lock = threading.Lock()

    @classmethod
    def create(
        cls, root: Path, document: dict[str, Any] | CanvasDocument, run_id: str | None = None
    ) -> RunStore:
        validated = (
            document
            if isinstance(document, CanvasDocument)
            else CanvasDocument.model_validate(document)
        )
        identifier = run_id or uuid4().hex
        path = Path(root) / identifier
        path.mkdir(parents=True, exist_ok=False)
        store = cls(path)
        store._write_json("document.json", validated.model_dump(mode="json"))
        store._write_json(
            "state.json",
            {
                "run_id": identifier,
                "status": "draft",
                "revision": 0,
                "created_at": _now(),
                "updated_at": _now(),
                "approval": None,
                "independent_review": None,
            },
        )
        store.append_event("run.created", "system", None, {"title": validated.metadata.title})
        return store

    def read_document(self) -> CanvasDocument:
        return CanvasDocument.model_validate(self._read_json("document.json"))

    def read_state(self) -> dict[str, Any]:
        return self._read_json("state.json")

    def session_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "state": self.read_state(),
            "document": self.read_document().model_dump(mode="json"),
        }

    def validation_issues(self) -> list[ValidationIssue]:
        document = self.read_document()
        issues = validate_document(document)
        if document.completion.require_independent_review:
            state = self.read_state()
            review = state.get("independent_review")
            if (
                review is None
                or review.get("status") != "passed"
                or review.get("revision") != state["revision"]
            ):
                issues.append(independent_review_issue())
        return issues

    def update_field(self, field_id: str, value: Any, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            state = self.read_state()
            self._ensure_editable(state)
            if state["revision"] != expected_revision:
                raise RevisionConflict(
                    f"Expected revision {expected_revision}, "
                    f"current revision is {state['revision']}"
                )
            document = self.read_document()
            matching = [field for field in document.fields() if field.id == field_id]
            if not matching:
                raise KeyError(field_id)
            if len(matching) > 1:
                raise ValueError(f"Field ID is not unique: {field_id}")
            field = matching[0]
            candidate_issues = validate_field_candidate(field, value)
            if candidate_issues:
                message = "; ".join(issue.message for issue in candidate_issues)
                raise ValueError(message)
            field.value = value
            field.provenance = "user-confirmed"
            field.review_status = "accepted"

            state["revision"] += 1
            state["status"] = "user-editing"
            state["updated_at"] = _now()
            state["approval"] = None
            state["independent_review"] = None
            self._write_json("document.json", document.model_dump(mode="json"))
            self._write_json("state.json", state)
            self.append_event(
                "field.updated",
                "user",
                field_id,
                {"value_changed": True, "provenance": "user-confirmed"},
            )
            return self.session_payload()

    def update_artifact(
        self, artifact_id: str, content: str, expected_revision: int
    ) -> dict[str, Any]:
        with self._lock:
            state = self.read_state()
            self._ensure_editable(state)
            if state["revision"] != expected_revision:
                raise RevisionConflict(
                    f"Expected revision {expected_revision}, "
                    f"current revision is {state['revision']}"
                )
            document = self.read_document()
            matching = [
                artifact
                for artifact in document.initialization.artifacts
                if artifact.id == artifact_id
            ]
            if not matching:
                raise KeyError(artifact_id)
            if len(matching) > 1:
                raise ValueError(f"Artifact ID is not unique: {artifact_id}")
            artifact = matching[0]
            artifact.content = content
            artifact.provenance = "user-confirmed"
            artifact.review_status = "accepted"

            state["revision"] += 1
            state["status"] = "user-editing"
            state["updated_at"] = _now()
            state["approval"] = None
            state["independent_review"] = None
            self._write_json("document.json", document.model_dump(mode="json"))
            self._write_json("state.json", state)
            self.append_event(
                "artifact.updated",
                "user",
                artifact_id,
                {"content_changed": True, "provenance": "user-confirmed"},
            )
            return self.session_payload()

    def approve(self, approved_by: str, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            state = self.read_state()
            self._ensure_editable(state)
            if state["revision"] != expected_revision:
                raise RevisionConflict(
                    f"Expected revision {expected_revision}, "
                    f"current revision is {state['revision']}"
                )
            issues = self.validation_issues()
            errors = [issue for issue in issues if issue.severity == "error"]
            if errors:
                raise ValidationFailed(errors)
            state["status"] = "approved"
            state["updated_at"] = _now()
            state["approval"] = {
                "approved_by": approved_by,
                "approved_at": _now(),
                "revision": expected_revision,
                "document_sha256": document_sha256(self.read_document()),
            }
            self._write_json("state.json", state)
            self.append_event(
                "run.approved",
                "user",
                None,
                {"approved_by": approved_by, "revision": expected_revision},
            )
            return self.session_payload()

    def begin_compilation(self, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            state = self.read_state()
            if state["revision"] != expected_revision:
                raise RevisionConflict(
                    f"Expected revision {expected_revision}, "
                    f"current revision is {state['revision']}"
                )
            if state["status"] == "compiled":
                raise RevisionConflict("The run is already compiled")
            if state["status"] != "approved":
                raise RevisionConflict(f"Cannot compile a run whose status is {state['status']!r}")
            approval = state.get("approval")
            if approval is None or approval.get("revision") != expected_revision:
                raise RevisionConflict("The current document revision has not been approved")
            current_digest = document_sha256(self.read_document())
            if approval.get("document_sha256") != current_digest:
                raise RevisionConflict("The approved document contents have changed")
            errors = [issue for issue in self.validation_issues() if issue.severity == "error"]
            if errors:
                raise RevisionConflict("The approved revision no longer satisfies readiness checks")
            state["status"] = "compiling"
            state["updated_at"] = _now()
            self._write_json("state.json", state)
            return dict(approval)

    def abort_compilation(self, expected_revision: int) -> None:
        with self._lock:
            state = self.read_state()
            if state["revision"] == expected_revision and state["status"] == "compiling":
                state["status"] = "approved"
                state["updated_at"] = _now()
                self._write_json("state.json", state)

    def mark_compiled(self, expected_revision: int) -> None:
        with self._lock:
            state = self.read_state()
            if state["revision"] != expected_revision:
                raise RevisionConflict(
                    f"Expected revision {expected_revision}, "
                    f"current revision is {state['revision']}"
                )
            if state["status"] != "compiling":
                raise RevisionConflict(f"Cannot compile a run whose status is {state['status']!r}")
            state["status"] = "compiled"
            state["updated_at"] = _now()
            self._write_json("state.json", state)
            self.append_event("run.compiled", "system", None, {"revision": expected_revision})

    def request_assistance(
        self,
        field_id: str,
        question: str,
        backend: AssistantBackend | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_editable(self.read_state())
            document = self.read_document()
            matching = [field for field in document.fields() if field.id == field_id]
            if not matching:
                raise KeyError(field_id)
            if len(matching) > 1:
                raise ValueError(f"Field ID is not unique: {field_id}")
            field = matching[0]
            if not field.assistance.enabled:
                raise PermissionError(f"Assistance is not enabled for {field_id}")
            request_id = uuid4().hex
            request = {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request_id,
                "operation": "field-assistance",
                "context": {
                    "document_title": document.metadata.title,
                    "document_kind": document.kind,
                    "revision": self.read_state()["revision"],
                    "field": field.model_dump(mode="json"),
                    "facilitator_prompt": field.assistance.prompt,
                    "question": question,
                },
            }
            request_dir = self.path / "requests"
            request_dir.mkdir(exist_ok=True)
            self._write_json_path(request_dir / f"{request_id}.json", request)
            self.append_event(
                "assistance.requested",
                "user",
                field_id,
                {"request_id": request_id},
            )

        if backend is None:
            return {"request_id": request_id, "status": "pending"}
        response = self._invoke_backend(backend, request, "assistance", field_id)
        response_dir = self.path / "responses"
        response_dir.mkdir(exist_ok=True)
        self._write_json_path(response_dir / f"{request_id}.json", response.model_dump(mode="json"))
        self.append_event(
            "assistance.completed",
            "agent",
            field_id,
            {"request_id": request_id, "suggestion_count": len(response.suggestions)},
        )
        return {
            "request_id": request_id,
            "status": "completed",
            "response": response.model_dump(mode="json"),
        }

    def request_review(
        self,
        role: str,
        focus: str,
        backend: AssistantBackend | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_editable(self.read_state())
            document = self.read_document()
            revision = self.read_state()["revision"]
            request_id = uuid4().hex
            request = {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request_id,
                "operation": "specification-review",
                "context": {
                    "role": role,
                    "focus": focus,
                    "revision": revision,
                    "document": document.model_dump(mode="json"),
                },
            }
            request_dir = self.path / "requests"
            request_dir.mkdir(exist_ok=True)
            self._write_json_path(request_dir / f"{request_id}.json", request)
            self.append_event(
                "review.requested",
                "user",
                None,
                {"request_id": request_id, "role": role, "revision": revision},
            )

        if backend is None:
            return {"request_id": request_id, "status": "pending"}
        response = self._invoke_backend(backend, request, "review", None)
        response_dir = self.path / "responses"
        response_dir.mkdir(exist_ok=True)
        self._write_json_path(response_dir / f"{request_id}.json", response.model_dump(mode="json"))
        review_applied = self._record_review_outcome(request_id, role, revision, response)
        self.append_event(
            "review.completed",
            "agent",
            None,
            {
                "request_id": request_id,
                "role": role,
                "question_count": len(response.questions),
                "review_applied": review_applied,
            },
        )
        return {
            "request_id": request_id,
            "status": "completed",
            "response": response.model_dump(mode="json"),
            "review_applied": review_applied,
        }

    def request_composition(
        self,
        focus: str,
        backend: AssistantBackend | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_editable(self.read_state())
            document = self.read_document()
            revision = self.read_state()["revision"]
            request_id = uuid4().hex
            request = {
                "contract": "agent-canvas-assistant/v1",
                "request_id": request_id,
                "operation": "initialization-compose",
                "context": {
                    "focus": focus,
                    "revision": revision,
                    "document": document.model_dump(mode="json"),
                },
            }
            request_dir = self.path / "requests"
            request_dir.mkdir(exist_ok=True)
            self._write_json_path(request_dir / f"{request_id}.json", request)
            self.append_event(
                "composition.requested",
                "user",
                None,
                {"request_id": request_id, "revision": revision},
            )

        if backend is None:
            return {"request_id": request_id, "status": "pending"}
        response = self._invoke_backend(backend, request, "composition", None)
        response_dir = self.path / "responses"
        response_dir.mkdir(exist_ok=True)
        self._write_json_path(response_dir / f"{request_id}.json", response.model_dump(mode="json"))
        self.append_event(
            "composition.completed",
            "agent",
            None,
            {
                "request_id": request_id,
                "disposition": response.disposition,
                "has_next_document": response.next_document is not None,
            },
        )
        return {
            "request_id": request_id,
            "status": "completed",
            "response": response.model_dump(mode="json"),
        }

    def apply_response(self, request_id: str, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            state = self.read_state()
            self._ensure_editable(state)
            if state["revision"] != expected_revision:
                raise RevisionConflict(
                    f"Expected revision {expected_revision}, "
                    f"current revision is {state['revision']}"
                )
            request_path = self.path / "requests" / f"{request_id}.json"
            response_path = self.path / "responses" / f"{request_id}.json"
            if not request_path.is_file() or not response_path.is_file():
                raise KeyError(request_id)
            request = self._read_json_path(request_path)
            if request.get("context", {}).get("revision") != expected_revision:
                raise RevisionConflict("The proposal was created for a different document revision")
            response = AssistantResponse.model_validate(self._read_json_path(response_path))
            if response.next_document is None:
                raise ValueError("The assistant response does not contain a proposed canvas")
            issues = validate_document(response.next_document)
            definition_errors = [
                issue for issue in issues if issue.code in PROPOSAL_DEFINITION_ERROR_CODES
            ]
            if definition_errors:
                raise ValidationFailed(definition_errors)

            state["revision"] += 1
            state["status"] = "user-editing"
            state["updated_at"] = _now()
            state["approval"] = None
            state["independent_review"] = None
            self._write_json("document.json", response.next_document.model_dump(mode="json"))
            self._write_json("state.json", state)
            self.append_event(
                "proposal.applied",
                "user",
                None,
                {"request_id": request_id, "source_revision": expected_revision},
            )
            return self.session_payload()

    def _record_review_outcome(
        self,
        request_id: str,
        role: str,
        source_revision: int,
        response: AssistantResponse,
    ) -> bool:
        if role != "critic":
            return False
        with self._lock:
            state = self.read_state()
            if state["revision"] != source_revision or state["status"] in {"compiling", "compiled"}:
                return False
            passed = response.disposition == "ready" and response.next_document is None
            state["independent_review"] = {
                "status": "passed" if passed else "changes-requested",
                "revision": source_revision,
                "request_id": request_id,
                "reviewed_at": _now(),
                "summary": response.summary,
            }
            if not passed and state.get("approval") is not None:
                state["approval"] = None
                state["status"] = "user-editing"
            state["updated_at"] = _now()
            self._write_json("state.json", state)
            return True

    def append_event(
        self,
        event_type: str,
        actor: str,
        target: str | None,
        summary: dict[str, Any],
    ) -> None:
        event = {
            "timestamp": _now(),
            "revision": self.read_state()["revision"],
            "type": event_type,
            "actor": actor,
            "target": target,
            "summary": summary,
        }
        with (self.path / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _invoke_backend(
        self,
        backend: AssistantBackend,
        request: dict[str, Any],
        operation: str,
        target: str | None,
    ) -> AssistantResponse:
        try:
            return backend.invoke(request)
        except Exception as exc:
            failure = {
                "contract": "agent-canvas-assistant-failure/v1",
                "request_id": request["request_id"],
                "operation": request["operation"],
                "failed_at": _now(),
                "error_type": type(exc).__name__,
                "message": str(exc)[:1000],
            }
            failure_dir = self.path / "failures"
            failure_dir.mkdir(exist_ok=True)
            self._write_json_path(failure_dir / f"{request['request_id']}.json", failure)
            self.append_event(
                f"{operation}.failed",
                "agent",
                target,
                {
                    "request_id": request["request_id"],
                    "error_type": type(exc).__name__,
                },
            )
            raise

    def _read_json(self, name: str) -> dict[str, Any]:
        return self._read_json_path(self.path / name)

    def _read_json_path(self, path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, name: str, value: dict[str, Any]) -> None:
        self._write_json_path(self.path / name, value)

    def _write_json_path(self, destination: Path, value: dict[str, Any]) -> None:
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(destination)

    @staticmethod
    def _ensure_editable(state: dict[str, Any]) -> None:
        if state["status"] in {"compiling", "compiled"}:
            raise RevisionConflict(f"Run status {state['status']!r} is terminal for editing")


def _now() -> str:
    return datetime.now(UTC).isoformat()
