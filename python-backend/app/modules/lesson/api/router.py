
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.modules.lesson.api.schemas import (
    LessonDocumentResponse,
    LessonReorderRequest,
    LessonResponse,
    LessonWriteRequest,
)
from app.modules.lesson.application.lesson_service import (
    LessonService,
    UploadedDocument,
)
from app.shared.auth.principal import AuthenticatedUser, principal_of
from app.shared.config.settings import get_settings
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.http.dependencies import get_db, require_teacher_or_admin
from app.shared.storage.documents import DocumentStorage

router = APIRouter(prefix="/api/v1", tags=["lesson"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def lesson_service(request: Request, session: Session = Depends(get_db)) -> LessonService:
    from app.modules.lesson.application.access_policy import LessonAccessPolicy

    settings = get_settings()
    return LessonService(
        session,
        settings,
        request.app.state.document_storage,
        LessonAccessPolicy(session),
    )


LessonServiceDep = Annotated[LessonService, Depends(lesson_service)]


async def read_upload(file: UploadFile) -> UploadedDocument:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:

        raise ApiException(ErrorCode.FILE_TOO_LARGE, "Maximum upload size exceeded")
    return UploadedDocument(
        filename=file.filename,
        content_type=file.content_type,
        content=content,
    )


@router.get(
    "/courses/{course_id}/lessons",
    response_model=list[LessonResponse],
)
def list_lessons(
    course_id: int, request: Request, service: LessonServiceDep
) -> list[LessonResponse]:
    return service.list_for_course(course_id, principal_of(request).user_id)


@router.post(
    "/courses/{course_id}/lessons",
    status_code=status.HTTP_201_CREATED,
    response_model=LessonResponse,
)
def create_lesson(
    course_id: int,
    payload: LessonWriteRequest,
    request: Request,
    service: LessonServiceDep,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> LessonResponse:
    return service.create(course_id, payload, principal_of(request).user_id)


@router.patch("/courses/{course_id}/lessons/order", response_model=list[LessonResponse])
def reorder_lessons(
    course_id: int,
    payload: LessonReorderRequest,
    request: Request,
    service: LessonServiceDep,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> list[LessonResponse]:
    return service.reorder(course_id, payload, principal_of(request).user_id)


@router.get("/lessons/{lesson_id}", response_model=LessonResponse)
def get_lesson(
    lesson_id: int, request: Request, service: LessonServiceDep
) -> LessonResponse:
    return service.get(lesson_id, principal_of(request).user_id)


@router.put("/lessons/{lesson_id}", response_model=LessonResponse)
def update_lesson(
    lesson_id: int,
    payload: LessonWriteRequest,
    request: Request,
    service: LessonServiceDep,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> LessonResponse:
    return service.update(lesson_id, payload, principal_of(request).user_id)


@router.delete("/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lesson(
    lesson_id: int,
    request: Request,
    service: LessonServiceDep,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> Response:
    service.delete(lesson_id, principal_of(request).user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/lessons/{lesson_id}/documents",
    response_model=list[LessonDocumentResponse],
)
def list_documents(
    lesson_id: int, request: Request, service: LessonServiceDep
) -> list[LessonDocumentResponse]:
    return service.list_documents(lesson_id, principal_of(request).user_id)


@router.post(
    "/lessons/{lesson_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=LessonDocumentResponse,
)
async def upload_document(
    lesson_id: int,
    request: Request,
    service: LessonServiceDep,
    file: Annotated[UploadFile, File()],
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> LessonDocumentResponse:
    upload = await read_upload(file)
    return service.upload_document(lesson_id, upload, principal_of(request).user_id)


@router.get("/documents/{document_id}/content")
def download_document(
    document_id: int, request: Request, service: LessonServiceDep
) -> Response:
    document = service.download_document(document_id, principal_of(request).user_id)
    from urllib.parse import quote


    ascii_name = document.original_name.encode("ascii", "replace").decode("ascii")
    ascii_name = ascii_name.replace('"', "'")
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(document.original_name)}"
    )
    return Response(
        content=document.content,
        media_type=document.media_type or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    request: Request,
    service: LessonServiceDep,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> Response:
    service.delete_document(document_id, principal_of(request).user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router", "DocumentStorage"]
