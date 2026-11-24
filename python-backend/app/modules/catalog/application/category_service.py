
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.catalog.api.schemas import (
    CategoryResponse,
    CreateCategoryRequest,
    UpdateCategoryRequest,
    category_response,
)
from app.shared.database.base import utcnow
from app.shared.database.models import Category
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.pagination import page_response, require_valid_pagination

_SORTABLE = {
    "created_at": Category.created_at,
    "createdAt": Category.created_at,
    "updated_at": Category.updated_at,
    "updatedAt": Category.updated_at,
    "id": Category.id,
    "name": Category.name,
}


class CategoryService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self, page: int, page_size: int, sort: str | None) -> dict:
        require_valid_pagination(page, page_size)
        total = self._session.scalar(select(func.count()).select_from(Category)) or 0
        rows = self._session.scalars(
            select(Category)
            .order_by(*_order_by(sort))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return page_response([category_response(row) for row in rows], page, page_size, total)

    def create(self, request: CreateCategoryRequest) -> CategoryResponse:
        name = request.name.strip()
        exists = self._session.scalar(
            select(func.count()).select_from(Category).where(Category.name == name)
        )
        if exists:
            raise ApiException(ErrorCode.INVALID_STATE, "Category name already exists")

        now = utcnow()
        category = Category(
            name=name,
            description=request.description,
            created_at=now,
            updated_at=now,
        )
        self._session.add(category)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ApiException(ErrorCode.INVALID_STATE, "Category name already exists") from exc
        return category_response(category)

    def update(self, category_id: int, request: UpdateCategoryRequest) -> CategoryResponse:
        category = self._session.get(Category, category_id)
        if category is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Category not found")

        if request.name is not None:
            name = request.name.strip()
            if not name:
                raise ApiException(ErrorCode.VALIDATION_ERROR, "Name must not be blank")
            conflict = self._session.scalar(
                select(func.count())
                .select_from(Category)
                .where(Category.name == name, Category.id != category_id)
            )
            if conflict:
                raise ApiException(ErrorCode.INVALID_STATE, "Category name already exists")
            category.name = name
        if request.description is not None:
            category.description = request.description

        category.updated_at = utcnow()
        self._session.flush()
        return category_response(category)

    def delete(self, category_id: int) -> None:
        category = self._session.get(Category, category_id)
        if category is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Category not found")
        self._session.delete(category)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ApiException(
                ErrorCode.RESOURCE_IN_USE, "Category is used by a course"
            ) from exc


def _order_by(sort: str | None) -> tuple:
    if not sort:
        return (Category.created_at.desc(), Category.id.desc())
    parts = [part.strip() for part in sort.split(",") if part.strip()]
    clauses = []
    seen_id = False
    index = 0
    while index < len(parts):
        property_name = parts[index]
        direction = "desc"
        if index + 1 < len(parts) and parts[index + 1].lower() in {"asc", "desc"}:
            direction = parts[index + 1].lower()
            index += 1
        index += 1
        column = _SORTABLE.get(property_name)
        if column is None:
            raise ApiException(ErrorCode.VALIDATION_ERROR, "Unsupported sort field")
        clauses.append(column.asc() if direction == "asc" else column.desc())
        if property_name == "id":
            seen_id = True
    if not seen_id:
        clauses.append(Category.id.desc())
    return tuple(clauses)
