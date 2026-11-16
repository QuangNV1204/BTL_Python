"""Khóa học, thumbnail, publication, archive, marketplace.

Gộp CourseService + CoursePublicationService + MarketplaceService +
CourseOwnerAssembler + ThumbnailService + CourseOwnership của Java.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.course.api.schemas import (
    CourseOutlineItem,
    CourseOwnerResponse,
    CoursePatchRequest,
    CoursePublicResponse,
    CourseWriteRequest,
    course_owner_response,
    course_public_response,
)
from app.shared.auth.principal import AuthenticatedUser
from app.shared.database.base import utcnow
from app.shared.database.hooks import after_commit
from app.shared.database.models import Category, Course, CourseMember, Lesson, User
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.pagination import page_response, require_valid_pagination
from app.shared.storage.images import ImageType
from app.shared.storage.local_file_storage import LocalFileStorage, StoredFile

logger = logging.getLogger("learningai.course")

MAX_QUERY_LENGTH = 200
_MARKETPLACE_SORT = {
    "price": Course.price,
    "title": Course.title,
    "updatedAt": Course.updated_at,
    "createdAt": Course.created_at,
}


class CourseService:
    def __init__(self, session: Session, storage: LocalFileStorage, max_thumbnail_bytes: int):
        self._session = session
        self._storage = storage
        self._max_thumbnail_bytes = max_thumbnail_bytes

    # ------------------------------------------------------------------ owner
    def require_owned(self, course_id: int, actor: AuthenticatedUser) -> Course:
        course = self._session.get(Course, course_id)
        if course is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Course not found")
        if not actor.is_admin and course.teacher_id != actor.user_id:
            raise ApiException(ErrorCode.FORBIDDEN, "Not the course owner")
        return course

    def create(self, request: CourseWriteRequest, actor: AuthenticatedUser) -> CourseOwnerResponse:
        if not actor.is_teacher_or_admin:
            raise ApiException(ErrorCode.FORBIDDEN, "Only teachers can manage courses")

        teacher = self._session.get(User, actor.user_id)
        if teacher is None:
            raise ApiException(ErrorCode.UNAUTHENTICATED, "User not found")
        category = self._require_category(request.category_id)

        now = utcnow()
        course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            title=request.title,
            description=request.description,
            price=request.price,
            is_published=False,
            created_at=now,
            updated_at=now,
        )
        course.teacher = teacher
        course.category = category
        self._session.add(course)
        self._session.flush()
        return self._owner_response(course)

    def update(
        self, course_id: int, request: CoursePatchRequest, actor: AuthenticatedUser
    ) -> CourseOwnerResponse:
        course = self.require_owned(course_id, actor)
        if request.title is not None:
            course.title = request.title
        if request.description is not None:
            course.description = request.description
        if request.price is not None:
            course.price = request.price
        if request.category_id is not None:
            course.category = self._require_category(request.category_id)
            course.category_id = request.category_id
        course.updated_at = utcnow()
        self._session.flush()
        return self._owner_response(course)

    def list_for_teaching(
        self, actor: AuthenticatedUser, page: int, page_size: int
    ) -> dict:
        require_valid_pagination(page, page_size)
        statement = select(Course)
        count_statement = select(func.count()).select_from(Course)
        if not actor.is_admin:
            statement = statement.where(Course.teacher_id == actor.user_id)
            count_statement = count_statement.where(Course.teacher_id == actor.user_id)

        total = self._session.scalar(count_statement) or 0
        courses = self._session.scalars(
            statement.order_by(Course.created_at.desc(), Course.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = self._owner_responses(list(courses))
        return page_response(items, page, page_size, total)

    def get_owned(self, course_id: int, actor: AuthenticatedUser) -> CourseOwnerResponse:
        return self._owner_response(self.require_owned(course_id, actor))

    def update_thumbnail(
        self, course_id: int, content: bytes, actor: AuthenticatedUser
    ) -> CourseOwnerResponse:
        course = self.require_owned(course_id, actor)
        if not content:
            raise ApiException(ErrorCode.VALIDATION_ERROR, "Thumbnail file is required")
        if len(content) > self._max_thumbnail_bytes:
            raise ApiException(ErrorCode.FILE_TOO_LARGE, "Thumbnail must be at most 5 MiB")
        image_type = ImageType.detect(content)
        if image_type is None:
            raise ApiException(
                ErrorCode.UNSUPPORTED_FILE_TYPE,
                "Thumbnail must be a JPEG, PNG or WebP image",
            )

        stored: StoredFile = self._storage.store(content, image_type.extension)
        previous_key = course.thumbnail_storage_key
        course.thumbnail_storage_key = stored.storage_key
        course.thumbnail_url = stored.url
        course.updated_at = utcnow()
        self._session.flush()
        response = self._owner_response(course)
        self._delete_after_commit(previous_key)
        return response

    def delete(self, course_id: int, actor: AuthenticatedUser) -> None:
        course = self.require_owned(course_id, actor)
        if course.is_published or course.archived_at is not None:
            raise ApiException(ErrorCode.INVALID_STATE, "Only draft courses can be deleted")
        enrolled = self._session.scalar(
            select(func.count())
            .select_from(CourseMember)
            .where(CourseMember.course_id == course_id)
        )
        if enrolled:
            raise ApiException(
                ErrorCode.INVALID_STATE, "Course already has enrolled students"
            )
        key = course.thumbnail_storage_key
        self._session.delete(course)
        self._session.flush()
        self._delete_after_commit(key)

    # ------------------------------------------------------------ publication
    def set_published(
        self, course_id: int, publish: bool, actor: AuthenticatedUser
    ) -> CourseOwnerResponse:
        course = self.require_owned(course_id, actor)
        if publish:
            if course.archived_at is not None:
                raise ApiException(
                    ErrorCode.INVALID_STATE, "Archived courses cannot be published"
                )
            if course.is_published:
                return self._owner_response(course)
            self._require_publishable(course)
            course.is_published = True
        else:
            course.is_published = False
        course.updated_at = utcnow()
        self._session.flush()
        return self._owner_response(course)

    def archive(self, course_id: int, actor: AuthenticatedUser) -> CourseOwnerResponse:
        course = self.require_owned(course_id, actor)
        if course.archived_at is not None:
            return self._owner_response(course)
        # Instant.now().truncatedTo(MICROS) — DATETIME(6) đã là microsecond.
        course.archived_at = utcnow()
        course.is_published = False
        course.updated_at = utcnow()
        self._session.flush()
        return self._owner_response(course)

    # ------------------------------------------------------------ marketplace
    def search(
        self,
        query: str | None,
        category_id: int | None,
        sort: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        require_valid_pagination(page, page_size)
        normalized = self._normalize_query(query)
        if category_id is not None and self._session.get(Category, category_id) is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Category not found")

        statement = select(Course).where(
            Course.is_published.is_(True), Course.archived_at.is_(None)
        )
        count_statement = select(func.count()).select_from(Course).where(
            Course.is_published.is_(True), Course.archived_at.is_(None)
        )
        if category_id is not None:
            statement = statement.where(Course.category_id == category_id)
            count_statement = count_statement.where(Course.category_id == category_id)
        if normalized:
            # LIKE với escape '!' và lower() — giống MarketplaceQueryRepository.
            pattern = "%" + _escape_like(normalized.lower()) + "%"
            condition = func.lower(Course.title).like(pattern, escape="!")
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)

        total = self._session.scalar(count_statement) or 0
        if total == 0:
            return page_response([], page, page_size, 0)

        courses = list(
            self._session.scalars(
                statement.order_by(*_order_by(sort))
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        course_ids = [course.id for course in courses]
        enrollments = self._enrollment_counts(course_ids)
        lessons = self._lesson_counts(course_ids)
        items = [
            course_public_response(
                course,
                total_students=enrollments.get(course.id, 0),
                lesson_count=lessons.get(course.id, 0),
            )
            for course in courses
        ]
        return page_response(items, page, page_size, total)

    def get_public_course(self, course_id: int) -> CoursePublicResponse:
        course = self._session.get(Course, course_id)
        if (
            course is None
            or not course.is_published
            or course.archived_at is not None
        ):
            raise ApiException(ErrorCode.NOT_FOUND, "Course not found")

        lessons = self._session.execute(
            select(Lesson.id, Lesson.title, Lesson.order_index)
            .where(Lesson.course_id == course_id)
            .order_by(Lesson.order_index.asc())
        ).all()
        outline = [
            CourseOutlineItem(id=str(row.id), title=row.title, order_index=row.order_index)
            for row in lessons
        ]
        return course_public_response(
            course,
            total_students=self._enrollment_count(course_id),
            lesson_count=len(outline),
            outline=outline,
        )

    # -------------------------------------------------------------- internals
    def _require_category(self, category_id: int) -> Category:
        category = self._session.get(Category, category_id)
        if category is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Category not found")
        return category

    def _require_publishable(self, course: Course) -> None:
        if not (course.title or "").strip():
            raise _not_publishable("title is required")
        if not (course.description or "").strip():
            raise _not_publishable("description is required")
        if course.category_id is None:
            raise _not_publishable("category is required")
        if not (course.thumbnail_storage_key or "").strip():
            raise _not_publishable("thumbnail is required")
        if course.price is not None and course.price > Decimal("0"):
            raise ApiException(
                ErrorCode.COURSE_NOT_FREE, "Only free courses can be published in this version"
            )
        if self._lesson_count(course.id) < 1:
            raise _not_publishable("at least one lesson is required")

    def _owner_response(self, course: Course) -> CourseOwnerResponse:
        return course_owner_response(
            course, self._lesson_count(course.id), self._enrollment_count(course.id)
        )

    def _owner_responses(self, courses: list[Course]) -> list[CourseOwnerResponse]:
        if not courses:
            return []
        ids = [course.id for course in courses]
        lessons = self._lesson_counts(ids)
        students = self._enrollment_counts(ids)
        return [
            course_owner_response(
                course, lessons.get(course.id, 0), students.get(course.id, 0)
            )
            for course in courses
        ]

    def _lesson_count(self, course_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(Lesson).where(Lesson.course_id == course_id)
            )
            or 0
        )

    def _lesson_counts(self, course_ids: list[int]) -> dict[int, int]:
        if not course_ids:
            return {}
        rows = self._session.execute(
            select(Lesson.course_id, func.count())
            .where(Lesson.course_id.in_(course_ids))
            .group_by(Lesson.course_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows}

    def _enrollment_count(self, course_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(CourseMember)
                .where(CourseMember.course_id == course_id)
            )
            or 0
        )

    def _enrollment_counts(self, course_ids: list[int]) -> dict[int, int]:
        if not course_ids:
            return {}
        rows = self._session.execute(
            select(CourseMember.course_id, func.count())
            .where(CourseMember.course_id.in_(course_ids))
            .group_by(CourseMember.course_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows}

    def _delete_after_commit(self, storage_key: str | None) -> None:
        if not storage_key:
            return
        after_commit(self._session, lambda key=storage_key: self._storage.delete(key))

    @staticmethod
    def _normalize_query(query: str | None) -> str | None:
        if query is None or not query.strip():
            return None
        trimmed = query.strip()
        if len(trimmed) > MAX_QUERY_LENGTH:
            raise ApiException(
                ErrorCode.VALIDATION_ERROR, "q must be at most 200 characters"
            )
        return trimmed


def _not_publishable(reason: str) -> ApiException:
    return ApiException(ErrorCode.INVALID_STATE, f"Course cannot be published: {reason}")


def _escape_like(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def _order_by(sort: str | None) -> tuple:
    """Sao MarketplaceQueryRepository.orderBy: chỉ price/title/updatedAt, mặc định createdAt."""
    clauses: list = []
    if sort and sort.strip():
        parts = [part.strip() for part in sort.strip().split(",", 1)]
        property_name = parts[0]
        ascending = len(parts) > 1 and parts[1].lower() == "asc"
        if property_name not in _MARKETPLACE_SORT:
            raise ApiException(ErrorCode.VALIDATION_ERROR, "Unsupported sort field")
        clauses.append(_MARKETPLACE_SORT[property_name].asc() if ascending
                       else _MARKETPLACE_SORT[property_name].desc())
    else:
        clauses.append(Course.created_at.desc())
    clauses.append(Course.id.desc())
    return tuple(clauses)
