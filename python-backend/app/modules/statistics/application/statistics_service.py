"""Thống kê theo quyền — sao StatisticsService.java.

SQL giữ nguyên; số liệu chỉ tính dữ liệu PUBLISHED/SUBMITTED như Java.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.auth.principal import AuthenticatedUser
from app.shared.database.base import utcnow
from app.shared.domain.enums import UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.http.serialization import format_instant


class StatisticsService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def course(self, course_id: int, actor: AuthenticatedUser) -> dict:
        self._require_course_owner(course_id, actor)
        enrolled = self._count(
            "SELECT COUNT(*) FROM course_members WHERE course_id = :id", course_id
        )
        quizzes = self._count(
            "SELECT COUNT(*) FROM quizzes q JOIN lessons l ON l.id = q.lesson_id "
            "WHERE l.course_id = :id AND q.status = 'PUBLISHED'",
            course_id,
        )
        submitted = self._count(
            "SELECT COUNT(*) FROM quiz_attempts a JOIN quizzes q ON q.id = a.quiz_id "
            "JOIN lessons l ON l.id = q.lesson_id "
            "WHERE l.course_id = :id AND a.status = 'SUBMITTED'",
            course_id,
        )
        completed = (
            0
            if quizzes == 0
            else self._count(
                """
                SELECT COUNT(*) FROM course_members m
                WHERE m.course_id = :id AND NOT EXISTS (
                  SELECT 1 FROM quizzes q JOIN lessons l ON l.id = q.lesson_id
                  WHERE l.course_id = :id AND q.status = 'PUBLISHED' AND NOT EXISTS (
                    SELECT 1 FROM quiz_attempts a
                    WHERE a.quiz_id = q.id AND a.student_id = m.student_id
                    AND a.status = 'SUBMITTED'))
                """,
                course_id,
            )
        )
        rate = (
            Decimal(0)
            if enrolled == 0 or quizzes == 0
            else (Decimal(completed) * Decimal(100) / Decimal(enrolled)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        return {
            "course_id": str(course_id),
            "enrolled_students": enrolled,
            "quiz_count": quizzes,
            "submitted_attempts": submitted,
            "completed_students": completed,
            "completion_rate": float(rate),
            "generated_at": format_instant(utcnow()),
        }

    def quiz(self, quiz_id: int, actor: AuthenticatedUser) -> dict:
        course_id = self._session.execute(
            text(
                "SELECT l.course_id FROM quizzes q JOIN lessons l ON l.id = q.lesson_id "
                "WHERE q.id = :id"
            ),
            {"id": quiz_id},
        ).scalar()
        if course_id is None:
            raise ApiException(ErrorCode.NOT_FOUND)
        self._require_course_owner(int(course_id), actor)

        aggregate = self._session.execute(
            text(
                """
                SELECT COUNT(*) AS submitted, COUNT(DISTINCT student_id) AS students,
                       AVG(score) AS average_score
                FROM quiz_attempts WHERE quiz_id = :id AND status = 'SUBMITTED'
                """
            ),
            {"id": quiz_id},
        ).one()
        best = self._session.execute(
            text(
                """
                SELECT student_id, MAX(score) AS score FROM quiz_attempts
                WHERE quiz_id = :id AND status = 'SUBMITTED'
                GROUP BY student_id ORDER BY score DESC, student_id
                """
            ),
            {"id": quiz_id},
        ).all()
        hardest = self._session.execute(
            text(
                """
                SELECT q.id, COUNT(*) AS wrong_count FROM questions q
                JOIN quiz_attempts a ON a.quiz_id = q.quiz_id AND a.status = 'SUBMITTED'
                LEFT JOIN student_answers s ON s.attempt_id = a.id AND s.question_id = q.id
                WHERE q.quiz_id = :id AND (s.id IS NULL OR s.is_correct = FALSE)
                GROUP BY q.id ORDER BY wrong_count DESC, q.id
                """
            ),
            {"id": quiz_id},
        ).all()

        average = aggregate.average_score
        return {
            "quiz_id": str(quiz_id),
            "submitted_attempts": int(aggregate.submitted),
            "unique_students": int(aggregate.students),
            "average_score": None if average is None else float(average),
            "best_scores": [
                {
                    "student_id": str(row.student_id),
                    "score": None if row.score is None else float(row.score),
                }
                for row in best
            ],
            "hardest_questions": [
                {"question_id": str(row.id), "wrong_count": int(row.wrong_count)}
                for row in hardest
            ],
            "generated_at": format_instant(utcnow()),
        }

    def system(self, actor: AuthenticatedUser) -> dict:
        if actor.role is not UserRole.ADMIN:
            raise ApiException(ErrorCode.FORBIDDEN)
        # One statement gives role counts over the same user snapshot. Keep the
        # existing totals unchanged for consumers that already depend on them.
        users = self._session.execute(
            text(
                "SELECT "
                "COUNT(CASE WHEN is_active = TRUE THEN 1 END) AS active_users, "
                "COUNT(CASE WHEN role = 'TEACHER' THEN 1 END) AS teachers, "
                "COUNT(CASE WHEN role = 'TEACHER' AND is_active = TRUE THEN 1 END) "
                "AS active_teachers, "
                "COUNT(CASE WHEN role = 'STUDENT' AND is_active = TRUE THEN 1 END) "
                "AS active_students FROM users"
            )
        ).one()
        return {
            "active_users": int(users.active_users),
            "teachers": int(users.teachers),
            "active_teachers": int(users.active_teachers),
            "active_students": int(users.active_students),
            "published_courses": self._scalar(
                "SELECT COUNT(*) FROM courses WHERE is_published = TRUE AND archived_at IS NULL"
            ),
            "enrollments": self._scalar("SELECT COUNT(*) FROM course_members"),
            "submitted_attempts": self._scalar(
                "SELECT COUNT(*) FROM quiz_attempts WHERE status = 'SUBMITTED'"
            ),
            "generated_at": format_instant(utcnow()),
        }

    def _require_course_owner(self, course_id: int, actor: AuthenticatedUser) -> None:
        owner = self._session.execute(
            text("SELECT teacher_id FROM courses WHERE id = :id"), {"id": course_id}
        ).scalar()
        if owner is None:
            raise ApiException(ErrorCode.NOT_FOUND)
        if actor.role is UserRole.ADMIN:
            return
        if actor.role is not UserRole.TEACHER or int(owner) != actor.user_id:
            raise ApiException(ErrorCode.FORBIDDEN)

    def _count(self, sql: str, course_id: int) -> int:
        return int(self._session.execute(text(sql), {"id": course_id}).scalar() or 0)

    def _scalar(self, sql: str) -> int:
        return int(self._session.execute(text(sql)).scalar() or 0)
