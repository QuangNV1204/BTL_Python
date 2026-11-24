
from __future__ import annotations

from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.shared.database.models import Course, CourseMember, Lesson, User
from app.shared.domain.enums import UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException


class LessonViewAccess(str, Enum):
    MANAGER = "MANAGER"
    ENROLLED_STUDENT = "ENROLLED_STUDENT"


class LessonAccessPolicy:
    def __init__(self, session: Session) -> None:
        self._session = session


    def lesson_context(self, lesson_id: int) -> Lesson:
        lesson = self._session.get(Lesson, lesson_id)
        if lesson is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Lesson not found")
        return lesson

    def course_teacher_id(self, course_id: int) -> int | None:
        return self._session.scalar(
            select(Course.teacher_id).where(Course.id == course_id)
        )

    def course_exists(self, course_id: int) -> bool:
        return bool(
            self._session.scalar(select(func.count()).select_from(Course).where(Course.id == course_id))
        )

    def is_enrolled(self, course_id: int, student_id: int) -> bool:
        return bool(
            self._session.scalar(
                select(func.count())
                .select_from(CourseMember)
                .where(
                    CourseMember.course_id == course_id,
                    CourseMember.student_id == student_id,
                )
            )
        )

    def role_of(self, user_id: int) -> UserRole:
        role = self._session.scalar(select(User.role).where(User.id == user_id))
        if role is None:
            raise ApiException(ErrorCode.UNAUTHENTICATED)
        return UserRole(role)


    def assert_can_manage_lesson(self, lesson_id: int, user_id: int) -> Lesson:
        lesson = self.lesson_context(lesson_id)
        role = self.role_of(user_id)
        if role is not UserRole.ADMIN and self.course_teacher_id(lesson.course_id) != user_id:
            raise ApiException(ErrorCode.FORBIDDEN)
        return lesson

    def assert_can_view_lesson(self, lesson_id: int, user_id: int) -> LessonViewAccess:
        lesson = self.lesson_context(lesson_id)
        return self._view_access(lesson.course_id, user_id)

    def assert_can_manage_course(self, course_id: int, user_id: int) -> None:
        if not self.course_exists(course_id):
            raise ApiException(ErrorCode.NOT_FOUND, "Course not found")
        role = self.role_of(user_id)
        if role is not UserRole.ADMIN and self.course_teacher_id(course_id) != user_id:
            raise ApiException(ErrorCode.FORBIDDEN)

    def assert_can_view_course(self, course_id: int, user_id: int) -> LessonViewAccess:
        if not self.course_exists(course_id):
            raise ApiException(ErrorCode.NOT_FOUND, "Course not found")
        return self._view_access(course_id, user_id)

    def _view_access(self, course_id: int, user_id: int) -> LessonViewAccess:
        role = self.role_of(user_id)
        if role is UserRole.ADMIN or self.course_teacher_id(course_id) == user_id:
            return LessonViewAccess.MANAGER
        if role is UserRole.STUDENT and self.is_enrolled(course_id, user_id):
            return LessonViewAccess.ENROLLED_STUDENT
        raise ApiException(
            ErrorCode.ENROLLMENT_REQUIRED
            if role is UserRole.STUDENT
            else ErrorCode.FORBIDDEN
        )
