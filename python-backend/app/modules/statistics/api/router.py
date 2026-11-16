"""Router statistics — khớp StatisticsController.java (TEACHER/ADMIN hoặc ADMIN)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.modules.statistics.application.statistics_service import StatisticsService
from app.shared.auth.principal import AuthenticatedUser, principal_of
from app.shared.http.dependencies import (
    get_db,
    require_admin,
    require_teacher_or_admin,
)
from app.shared.validation.validators import parse_positive_id

router = APIRouter(prefix="/api/v1/statistics", tags=["statistics"])


def _service(session: Session = Depends(get_db)) -> StatisticsService:
    return StatisticsService(session)


Service = Annotated[StatisticsService, Depends(_service)]


@router.get("/courses/{course_id}")
def course_statistics(
    course_id: str,
    request: Request,
    service: Service,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> dict:
    return service.course(parse_positive_id(course_id, "id"), principal_of(request))


@router.get("/quizzes/{quiz_id}")
def quiz_statistics(
    quiz_id: str,
    request: Request,
    service: Service,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> dict:
    return service.quiz(parse_positive_id(quiz_id, "id"), principal_of(request))


@router.get("/system")
def system_statistics(
    service: Service, actor: AuthenticatedUser = Depends(require_admin)
) -> dict:
    return service.system(actor)
