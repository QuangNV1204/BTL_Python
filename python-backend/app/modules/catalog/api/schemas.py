"""Category request/response — sao Create/UpdateCategoryRequest và CategoryResponse."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateCategoryRequest(_Request):
    name: str = Field(max_length=120)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value


class UpdateCategoryRequest(_Request):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = None


class CategoryResponse(BaseModel):
    id: str
    name: str
    description: str | None


def category_response(category) -> CategoryResponse:  # noqa: ANN001
    return CategoryResponse(
        id=str(category.id), name=category.name, description=category.description
    )
