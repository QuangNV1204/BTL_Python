"""Schema khóa học — CourseOwnerResponse / CoursePublicResponse của Java."""

from __future__ import annotations

from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.shared.http.serialization import Instant, PriceStr
from app.shared.validation.validators import codepoint_length


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CourseWriteRequest(_Request):
    title: str = Field(max_length=200)
    description: str
    category_id: int = Field(validation_alias=AliasChoices("category_id", "categoryId"))
    price: Decimal

    @field_validator("title", "description")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("price")
    @classmethod
    def _price_range(cls, value: Decimal) -> Decimal:
        return _check_price(value)


class CoursePatchRequest(_Request):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    category_id: int | None = Field(
        default=None, validation_alias=AliasChoices("category_id", "categoryId")
    )
    price: Decimal | None = None

    @field_validator("price")
    @classmethod
    def _price_range(cls, value: Decimal | None) -> Decimal | None:
        return value if value is None else _check_price(value)


class CoursePublicationRequest(_Request):
    is_published: bool = Field(validation_alias=AliasChoices("is_published", "isPublished"))


class CourseArchiveRequest(_Request):
    archived: bool


class CourseOwnerResponse(BaseModel):
    id: str
    title: str
    description: str
    category_id: str
    category_name: str
    teacher_id: str
    teacher_name: str
    thumbnail_url: str | None
    price: PriceStr
    is_published: bool
    lesson_count: int
    total_students: int
    archived_at: Instant | None
    created_at: Instant
    updated_at: Instant


class CourseCategory(BaseModel):
    id: str
    name: str


class CourseTeacher(BaseModel):
    id: str
    full_name: str


class CourseOutlineItem(BaseModel):
    id: str
    title: str
    order_index: int


class CoursePublicResponse(BaseModel):
    id: str
    title: str
    description: str
    category: CourseCategory
    teacher: CourseTeacher
    thumbnail_url: str | None
    price: PriceStr
    currency: str
    total_students: int
    # @JsonInclude(NON_NULL) của Java: field null thì không xuất hiện trong JSON.
    outline: list[CourseOutlineItem] | None = Field(default=None, exclude_if=lambda v: v is None)
    lesson_count: int | None = Field(default=None, exclude_if=lambda v: v is None)
    archived_at: Instant | None = Field(default=None, exclude_if=lambda v: v is None)


def _check_price(value: Decimal) -> Decimal:
    """@DecimalMin("0.00") + @Digits(integer=12, fraction=2)."""
    if value < Decimal("0"):
        raise ValueError("must be greater than or equal to 0.00")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:  # noqa: PLR2004
        raise ValueError("numeric value out of bounds (max 2 fraction digits)")
    if isinstance(exponent, int) and len(value.as_tuple().digits) - max(-exponent, 0) > 12:  # noqa: PLR2004
        raise ValueError("numeric value out of bounds (max 12 integer digits)")
    return value


def course_owner_response(course, lesson_count: int, total_students: int) -> CourseOwnerResponse:  # noqa: ANN001
    return CourseOwnerResponse(
        id=str(course.id),
        title=course.title,
        description=course.description,
        category_id=str(course.category_id),
        category_name=course.category.name,
        teacher_id=str(course.teacher_id),
        teacher_name=course.teacher.full_name,
        thumbnail_url=course.thumbnail_url,
        price=course.price,
        is_published=bool(course.is_published),
        lesson_count=lesson_count,
        total_students=total_students,
        archived_at=course.archived_at,
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


def course_public_response(
    course,  # noqa: ANN001
    *,
    total_students: int,
    lesson_count: int | None = None,
    outline: list[CourseOutlineItem] | None = None,
) -> CoursePublicResponse:
    return CoursePublicResponse(
        id=str(course.id),
        title=course.title,
        description=course.description,
        category=CourseCategory(id=str(course.category.id), name=course.category.name),
        teacher=CourseTeacher(id=str(course.teacher.id), full_name=course.teacher.full_name),
        thumbnail_url=course.thumbnail_url,
        price=course.price,
        currency="VND",
        total_students=total_students,
        outline=outline,
        lesson_count=lesson_count,
        archived_at=course.archived_at,
    )


def _unused(value: str) -> int:
    return codepoint_length(value)
