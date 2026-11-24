
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.modules.enrollment.application.enrollment_service import EnrollmentService
from app.shared.auth.principal import AuthenticatedUser, principal_of
from app.shared.http.dependencies import (
    get_db,
    require_student,
    require_teacher_or_admin,
)

router = APIRouter(prefix="/api/v1", tags=["enrollment"])


def _service(session: Session = Depends(get_db)) -> EnrollmentService:
    return EnrollmentService(session)


Service = Annotated[EnrollmentService, Depends(_service)]


@router.post("/courses/{course_id}/enroll")
def enroll(
    course_id: int,
    response: Response,
    service: Service,
    actor: AuthenticatedUser = Depends(require_student),
) -> dict:
    payload, created = service.enroll(course_id, actor)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return payload


@router.get("/users/me/courses")
def my_courses(
    service: Service,
    actor: AuthenticatedUser = Depends(require_student),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
) -> dict:
    return service.list_mine(actor, page, page_size)


@router.get("/courses/{course_id}/members")
def course_members(
    course_id: int,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
) -> dict:
    return service.list_members(course_id, actor, page, page_size)


__all__ = ["router", "principal_of", "Request"]
