"""Tải thumbnail công khai — khớp FileController.java (GET /api/v1/files/{key})."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.shared.database.models import Course
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.http.dependencies import get_db
from app.shared.storage.images import media_type_for_key

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.get("/{storage_key}")
def download_thumbnail(
    storage_key: str,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    # Chỉ phục vụ file đang là thumbnail của một khóa học.
    exists = session.scalar(
        select(func.count())
        .select_from(Course)
        .where(Course.thumbnail_storage_key == storage_key)
    )
    if not exists:
        raise ApiException(ErrorCode.NOT_FOUND, "File not found")

    storage = request.app.state.file_storage
    content = storage.load(storage_key)
    if content is None:  # pragma: no cover - storage.load ném StorageException
        raise ApiException(ErrorCode.NOT_FOUND, "File not found")

    return Response(
        content=content,
        media_type=media_type_for_key(storage_key) or "application/octet-stream",
        headers={
            "Cache-Control": "public, max-age=2592000",
            "X-Content-Type-Options": "nosniff",
        },
    )
