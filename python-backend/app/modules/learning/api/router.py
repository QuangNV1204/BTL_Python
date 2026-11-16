"""Router attempt — khớp AttemptController.java."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.modules.learning.api.schemas import SubmitAttemptRequest
from app.modules.learning.application.attempt_service import AttemptService
from app.shared.auth.principal import AuthenticatedUser, principal_of
from app.shared.error.exceptions import ApiException
from app.shared.http.dependencies import get_db, require_student
from app.shared.validation.validators import parse_positive_id

router = APIRouter(prefix="/api/v1", tags=["learning"])


def _service(session: Session = Depends(get_db)) -> AttemptService:
    return AttemptService(session)


Service = Annotated[AttemptService, Depends(_service)]


def _optional_positive(value: str | None, field_name: str) -> int | None:
    return None if value is None else parse_positive_id(value, field_name)


@router.get("/users/me/attempts")
def history(
    request: Request,
    service: Service,
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    quiz_id: str | None = Query(default=None),
    course_id: str | None = Query(default=None),
) -> dict:
    return service.history(
        principal_of(request),
        page,
        page_size,
        _optional_positive(quiz_id, "quiz_id"),
        _optional_positive(course_id, "course_id"),
    )


@router.post("/quizzes/{quiz_id}/attempts")
def start_attempt(
    quiz_id: str,
    response: Response,
    service: Service,
    actor: AuthenticatedUser = Depends(require_student),
) -> dict:
    result = service.start(parse_positive_id(quiz_id, "quiz_id"), actor)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    if result.created:
        response.headers["Location"] = f"/api/v1/attempts/{result.attempt.id}"
    return result.attempt.model_dump(mode="json")


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(
    attempt_id: str,
    response: Response,
    service: Service,
    actor: AuthenticatedUser = Depends(require_student),
    body: Any = Body(...),
) -> dict:
    result = service.submit(
        parse_positive_id(attempt_id, "attempt_id"),
        SubmitAttemptRequest.from_json(body),
        actor,
    )
    return result.model_dump(mode="json")


@router.get("/attempts/{attempt_id}")
def get_attempt(attempt_id: str, request: Request, service: Service) -> dict:
    return service.get(parse_positive_id(attempt_id, "attempt_id"), principal_of(request))


__all__ = ["router", "ApiException"]
