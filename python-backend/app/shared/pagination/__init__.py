
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException

T = TypeVar("T")


@dataclass
class Page(Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


def require_valid_pagination(page: int, page_size: int) -> None:
    if page < 1 or page_size < 1 or page_size > 100:
        raise ApiException(
            ErrorCode.VALIDATION_ERROR,
            "page must be >= 1 and page_size must be between 1 and 100",
        )


def page_response(items: list[Any], page: int, page_size: int, total: int) -> dict[str, Any]:
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def offset_of(page: int, page_size: int) -> int:
    return max(page - 1, 0) * page_size
