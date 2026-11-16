"""Router course/marketplace/thumbnail — khớp CourseController + MarketplaceController."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.modules.course.api.schemas import (
    CourseArchiveRequest,
    CourseOwnerResponse,
    CoursePatchRequest,
    CoursePublicationRequest,
    CoursePublicResponse,
    CourseWriteRequest,
)
from app.modules.course.application.course_service import CourseService
from app.shared.auth.principal import (
    AuthenticatedUser,
    optional_principal,
    principal_of,
)
from app.shared.config.settings import get_settings
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.http.dependencies import get_db, require_teacher_or_admin
from app.shared.validation.validators import parse_positive_id

router = APIRouter(prefix="/api/v1", tags=["course"])


def _service(request: Request, session: Session = Depends(get_db)) -> CourseService:
    return CourseService(
        session, request.app.state.file_storage, get_settings().max_thumbnail_bytes
    )


Service = Annotated[CourseService, Depends(_service)]


@router.post("/courses", status_code=status.HTTP_201_CREATED, response_model=CourseOwnerResponse)
def create_course(
    payload: CourseWriteRequest,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> CourseOwnerResponse:
    return service.create(payload, actor)


@router.patch("/courses/{course_id}", response_model=CourseOwnerResponse)
def update_course(
    course_id: int,
    payload: CoursePatchRequest,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> CourseOwnerResponse:
    return service.update(course_id, payload, actor)


@router.get("/teaching/courses")
def list_for_teaching(
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
) -> dict:
    return service.list_for_teaching(actor, page, page_size)


@router.get("/teaching/courses/{course_id}", response_model=CourseOwnerResponse)
def get_owned_course(
    course_id: int,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> CourseOwnerResponse:
    return service.get_owned(course_id, actor)


@router.post(
    "/courses/{course_id}/thumbnail",
    response_model=CourseOwnerResponse,
)
async def upload_thumbnail(
    course_id: int,
    service: Service,
    file: Annotated[UploadFile, File()],
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> CourseOwnerResponse:
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise ApiException(ErrorCode.FILE_TOO_LARGE, "Maximum upload size exceeded")
    return service.update_thumbnail(course_id, content, actor)


@router.patch("/courses/{course_id}/publication", response_model=CourseOwnerResponse)
def set_publication(
    course_id: int,
    payload: CoursePublicationRequest,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> CourseOwnerResponse:
    return service.set_published(course_id, payload.is_published, actor)


@router.patch("/courses/{course_id}/archive", response_model=CourseOwnerResponse)
def archive_course(
    course_id: int,
    payload: CourseArchiveRequest,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> CourseOwnerResponse:
    if payload.archived is not True:
        raise ApiException(ErrorCode.VALIDATION_ERROR, "Only archived=true is supported")
    return service.archive(course_id, actor)


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: int,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> Response:
    service.delete(course_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------- marketplace (public)
@router.get("/courses")
def search_courses(
    service: Service,
    q: str | None = Query(default=None),
    # Path param của Java là Long; giá trị không phải số phải thành 400 VALIDATION_ERROR.
    category_id: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
) -> dict:
    parsed_category = (
        None if category_id is None else parse_positive_id(category_id, "category_id")
    )
    return service.search(q, parsed_category, sort, page, page_size)


@router.get("/courses/{course_id}", response_model=CoursePublicResponse)
def get_public_course(course_id: int, service: Service) -> CoursePublicResponse:
    return service.get_public_course(course_id)


__all__ = ["router", "optional_principal", "principal_of"]
