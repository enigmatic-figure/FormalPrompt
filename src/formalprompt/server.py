from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from formalprompt.assistant import AssistantBackend, AssistantProtocolError
from formalprompt.compiler import ApprovalRequired, compile_run
from formalprompt.store import RevisionConflict, RunStore, ValidationFailed

STATIC_DIRECTORY = Path(__file__).parent / "static"


class FieldUpdate(BaseModel):
    value: Any
    expected_revision: int = Field(ge=0)


class ArtifactUpdate(BaseModel):
    content: str
    expected_revision: int = Field(ge=0)


class ApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=0)


class CompileRequest(BaseModel):
    expected_revision: int = Field(ge=0)


class AssistanceRequest(BaseModel):
    field_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=10_000)


class ReviewRequest(BaseModel):
    role: Literal["facilitator", "critic"]
    focus: str = Field(min_length=1, max_length=10_000)


class CompositionRequest(BaseModel):
    focus: str = Field(min_length=1, max_length=10_000)


class ApplyProposalRequest(BaseModel):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    expected_revision: int = Field(ge=0)


def create_app(
    store: RunStore,
    token: str,
    assistant: AssistantBackend | None = None,
    reviewer: AssistantBackend | None = None,
) -> FastAPI:
    app = FastAPI(title="FormalPrompt", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security_headers(request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def authorize(authorization: str | None = Header(default=None)) -> None:
        scheme, _, candidate = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(candidate, token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A valid run token is required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/api/session", dependencies=[Depends(authorize)])
    def get_session() -> dict:
        return store.session_payload()

    @app.get("/api/validation", dependencies=[Depends(authorize)])
    def get_validation() -> dict:
        issues = store.validation_issues()
        return {
            "ready": not any(issue.severity == "error" for issue in issues),
            "issues": [issue.model_dump() for issue in issues],
        }

    @app.patch("/api/fields/{field_id}", dependencies=[Depends(authorize)])
    def update_field(field_id: str, update: FieldUpdate) -> dict:
        try:
            return store.update_field(field_id, update.value, update.expected_revision)
        except RevisionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown field"
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

    @app.patch("/api/artifacts/{artifact_id}", dependencies=[Depends(authorize)])
    def update_artifact(artifact_id: str, update: ArtifactUpdate) -> dict:
        try:
            return store.update_artifact(artifact_id, update.content, update.expected_revision)
        except RevisionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown artifact"
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

    @app.post("/api/approve", dependencies=[Depends(authorize)])
    def approve(request: ApprovalRequest) -> dict:
        try:
            return store.approve(request.approved_by, request.expected_revision)
        except RevisionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ValidationFailed as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "message": str(exc),
                    "issues": [issue.model_dump() for issue in exc.issues],
                },
            ) from exc

    @app.post("/api/compile", dependencies=[Depends(authorize)])
    def compile_document(request: CompileRequest) -> dict:
        try:
            return compile_run(store, request.expected_revision)
        except (RevisionConflict, ApprovalRequired) as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.post("/api/assistance", dependencies=[Depends(authorize)])
    def request_assistance(request: AssistanceRequest) -> JSONResponse:
        try:
            result = store.request_assistance(request.field_id, request.question, assistant)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown field"
            ) from exc
        except RevisionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except (ValueError, PermissionError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
        except AssistantProtocolError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        return JSONResponse(
            status_code=202 if result["status"] == "pending" else 200, content=result
        )

    @app.post("/api/review", dependencies=[Depends(authorize)])
    def request_review(request: ReviewRequest) -> JSONResponse:
        try:
            backend = reviewer if request.role == "critic" and reviewer is not None else assistant
            result = store.request_review(request.role, request.focus, backend)
        except RevisionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except AssistantProtocolError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        return JSONResponse(
            status_code=202 if result["status"] == "pending" else 200, content=result
        )

    @app.post("/api/compose", dependencies=[Depends(authorize)])
    def request_composition(request: CompositionRequest) -> JSONResponse:
        try:
            result = store.request_composition(request.focus, assistant)
        except RevisionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except AssistantProtocolError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        return JSONResponse(
            status_code=202 if result["status"] == "pending" else 200, content=result
        )

    @app.post("/api/proposals/apply", dependencies=[Depends(authorize)])
    def apply_proposal(request: ApplyProposalRequest) -> dict:
        try:
            return store.apply_response(request.request_id, request.expected_revision)
        except RevisionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown proposal"
            ) from exc
        except (ValueError, ValidationFailed) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIRECTORY / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")

    return app
