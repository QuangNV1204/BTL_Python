
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.modules.catalog.api.schemas import (
    CategoryResponse,
    CreateCategoryRequest,
    UpdateCategoryRequest,
)
from app.modules.catalog.application.category_service import CategoryService
from app.shared.auth.principal import AuthenticatedUser
from app.shared.http.dependencies import get_db, require_admin

router = APIRouter(prefix="/api/v1/categories", tags=["catalog"])


def _service(session: Session = Depends(get_db)) -> CategoryService:
    return CategoryService(session)


Service = Annotated[CategoryService, Depends(_service)]


@router.get("")
def list_categories(
    service: Service,
    page: int = Query(default=1),
    page_size: int = Query(default=10),
    sort: str | None = Query(default=None),
) -> dict:
    return service.list(page, page_size, sort)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CategoryResponse)
def create_category(
    payload: CreateCategoryRequest,
    service: Service,
    _: AuthenticatedUser = Depends(require_admin),
) -> CategoryResponse:
    return service.create(payload)


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    payload: UpdateCategoryRequest,
    service: Service,
    _: AuthenticatedUser = Depends(require_admin),
) -> CategoryResponse:
    return service.update(category_id, payload)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    service: Service,
    _: AuthenticatedUser = Depends(require_admin),
) -> Response:
    service.delete(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
