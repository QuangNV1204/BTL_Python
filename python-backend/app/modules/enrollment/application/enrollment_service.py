
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.course.api.schemas import CoursePublicResponse, course_public_response
from app.shared.auth.principal import AuthenticatedUser
from app.shared.database.base import utcnow
from app.shared.database.models import Course, CourseMember, Lesson, User
from app.shared.domain.enums import UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.pagination import page_response, require_valid_pagination

logger = logging.getLogger("learningai.enrollment")


class EnrollmentService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enroll(self, course_id: int, actor: AuthenticatedUser) -> tuple[dict, bool]:
        if actor.role is not UserRole.STUDENT:
            raise ApiException(ErrorCode.FORBIDDEN, "Only students can enroll in courses")

        course = self._session.get(Course, course_id)
        if (
            course is None
            or not course.is_published
            or course.archived_at is not None
        ):

            raise ApiException(ErrorCode.NOT_FOUND, "Course not found")
        if course.price is not None and course.price > Decimal("0"):
            raise ApiException(
                ErrorCode.COURSE_NOT_FREE, "Only free courses can be enrolled"
            )

        existing = self._member(course_id, actor.user_id)
        if existing is not None:
            return self._enrollment_payload(existing), False

        now = utcnow()
        member = CourseMember(
            course_id=course_id, student_id=actor.user_id, enrolled_at=now
        )
        self._session.add(member)
        try:
            self._session.flush()
        except IntegrityError:

            logger.debug("Concurrent enrollment for course %s student %s", course_id, actor.user_id)
            self._session.rollback()
            winner = self._member(course_id, actor.user_id)
            if winner is None:
                raise ApiException(
                    ErrorCode.INVALID_STATE,
                    "Enrollment conflicted and could not be read back",
                )
            return self._enrollment_payload(winner), False
        return self._enrollment_payload(member), True

    def list_mine(
        self, actor: AuthenticatedUser, page: int, page_size: int
    ) -> dict:
        require_valid_pagination(page, page_size)
        total = int(
            self._session.scalar(
                select(func.count())
                .select_from(CourseMember)
                .where(CourseMember.student_id == actor.user_id)
            )
            or 0
        )
        rows = self._session.execute(
            select(Course, CourseMember.enrolled_at)
            .join(CourseMember, CourseMember.course_id == Course.id)
            .where(CourseMember.student_id == actor.user_id)
            .order_by(CourseMember.enrolled_at.desc(), Course.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        items = []
        for course, enrolled_at in rows:
            payload = course_public_response(
                course,
                total_students=self._enrollment_count(course.id),
                lesson_count=self._lesson_count(course.id),
            ).model_dump(mode="json")

            payload["enrolled_at"] = _instant(enrolled_at)
            items.append(payload)
        return page_response(items, page, page_size, total)

    def list_members(
        self, course_id: int, actor: AuthenticatedUser, page: int, page_size: int
    ) -> dict:
        require_valid_pagination(page, page_size)
        course = self._session.get(Course, course_id)
        if course is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Course not found")
        if not actor.is_admin and course.teacher_id != actor.user_id:
            raise ApiException(ErrorCode.FORBIDDEN, "Not the course owner")

        total = int(
            self._session.scalar(
                select(func.count())
                .select_from(CourseMember)
                .where(CourseMember.course_id == course.id)
            )
            or 0
        )
        rows = self._session.execute(
            select(CourseMember.student_id, User.full_name, CourseMember.enrolled_at)
            .join(User, User.id == CourseMember.student_id)
            .where(CourseMember.course_id == course.id)
            .order_by(CourseMember.enrolled_at.asc(), CourseMember.student_id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = [
            {
                "course_id": str(course.id),
                "student_id": str(student_id),
                "full_name": full_name,
                "enrolled_at": _instant(enrolled_at),
            }
            for student_id, full_name, enrolled_at in rows
        ]
        return page_response(items, page, page_size, total)


    def _member(self, course_id: int, student_id: int) -> CourseMember | None:
        return self._session.scalars(
            select(CourseMember).where(
                CourseMember.course_id == course_id,
                CourseMember.student_id == student_id,
            )
        ).first()

    @staticmethod
    def _enrollment_payload(member: CourseMember) -> dict:
        return {
            "course_id": str(member.course_id),
            "student_id": str(member.student_id),
            "enrolled_at": _instant(member.enrolled_at),
        }

    def _enrollment_count(self, course_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(CourseMember)
                .where(CourseMember.course_id == course_id)
            )
            or 0
        )

    def _lesson_count(self, course_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(Lesson).where(Lesson.course_id == course_id)
            )
            or 0
        )


def _instant(value) -> str | None:
    from app.shared.http.serialization import format_instant

    return format_instant(value)


__all__ = ["EnrollmentService", "CoursePublicResponse"]
