"""Làm bài, chấm điểm, xem lại và lịch sử — sao AttemptService.java."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.learning.api.schemas import (
    AttemptResponse,
    AttemptResultResponse,
    AttemptSummaryResponse,
    ReviewItem,
    ReviewOption,
    SubmitAttemptRequest,
)
from app.shared.auth.principal import AuthenticatedUser
from app.shared.database.base import utcnow
from app.shared.database.models import (
    Course,
    CourseMember,
    Lesson,
    Question,
    QuestionOption,
    Quiz,
    QuizAttempt,
    StudentAnswer,
)
from app.shared.domain.enums import AttemptStatus, QuizStatus, UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.pagination import page_response, require_valid_pagination

logger = logging.getLogger("learningai.attempt")


@dataclass
class StartResult:
    attempt: AttemptResponse
    created: bool


class AttemptService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ----------------------------------------------------------------- history
    def history(
        self,
        actor: AuthenticatedUser,
        page: int,
        page_size: int,
        quiz_id: int | None,
        course_id: int | None,
    ) -> dict:
        student = self._current_student(actor)
        require_valid_pagination(page, page_size)

        base = (
            select(QuizAttempt, Quiz.title, Course.id, Course.title)
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .join(Lesson, Lesson.id == Quiz.lesson_id)
            .join(Course, Course.id == Lesson.course_id)
            .where(QuizAttempt.student_id == student.user_id)
        )
        count_statement = (
            select(func.count())
            .select_from(QuizAttempt)
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .join(Lesson, Lesson.id == Quiz.lesson_id)
            .join(Course, Course.id == Lesson.course_id)
            .where(QuizAttempt.student_id == student.user_id)
        )
        if quiz_id is not None:
            base = base.where(QuizAttempt.quiz_id == quiz_id)
            count_statement = count_statement.where(QuizAttempt.quiz_id == quiz_id)
        if course_id is not None:
            base = base.where(Course.id == course_id)
            count_statement = count_statement.where(Course.id == course_id)

        total = self._session.scalar(count_statement) or 0
        rows = self._session.execute(
            base.order_by(QuizAttempt.started_at.desc(), QuizAttempt.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = [
            AttemptSummaryResponse(
                id=str(attempt.id),
                quiz_id=str(attempt.quiz_id),
                quiz_title=quiz_title,
                course_id=str(course_id_value),
                course_title=course_title,
                status=AttemptStatus(attempt.status),
                score=attempt.score,
                started_at=attempt.started_at,
                submitted_at=attempt.submitted_at,
            )
            for attempt, quiz_title, course_id_value, course_title in rows
        ]
        return page_response(items, page, page_size, total)

    # ------------------------------------------------------------------- start
    def start(self, quiz_id: int, actor: AuthenticatedUser) -> StartResult:
        student = self._current_student(actor)
        quiz = self._session.scalars(
            select(Quiz).where(Quiz.id == quiz_id).with_for_update()
        ).first()
        if quiz is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Quiz not found")

        course_id = self._lesson_course_id(quiz.lesson_id)
        if course_id is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Lesson not found")
        if not self._is_enrolled(course_id, student.user_id):
            raise ApiException(ErrorCode.ENROLLMENT_REQUIRED)

        existing = self._session.scalars(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.student_id == student.user_id,
                QuizAttempt.status == AttemptStatus.IN_PROGRESS.value,
            )
        ).first()
        if existing is not None:
            return StartResult(_to_attempt(existing), False)

        if quiz.status != QuizStatus.PUBLISHED.value:
            raise ApiException(
                ErrorCode.INVALID_STATE, "Only PUBLISHED quizzes can start new attempts"
            )
        question_count = self._question_count(quiz_id)
        if question_count < 1:
            raise ApiException(ErrorCode.INVALID_STATE, "Quiz has no questions")

        attempt = QuizAttempt(
            quiz_id=quiz_id,
            student_id=student.user_id,
            status=AttemptStatus.IN_PROGRESS.value,
            total_questions=question_count,
            started_at=utcnow(),
            version=0,
        )
        self._session.add(attempt)
        self._session.flush()
        return StartResult(_to_attempt(attempt), True)

    # ------------------------------------------------------------------ submit
    def submit(
        self, attempt_id: int, request: SubmitAttemptRequest, actor: AuthenticatedUser
    ) -> AttemptResultResponse:
        student = self._current_student(actor)
        attempt = self._owned_attempt_for_update(attempt_id, student.user_id)
        quiz = self._session.get(Quiz, attempt.quiz_id)
        if quiz is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Quiz not found")

        questions = self._questions(quiz.id)
        options_by_question = self._load_options(questions)
        if attempt.status == AttemptStatus.SUBMITTED.value:
            return self._stored_result(attempt, quiz, questions, options_by_question)

        selected = self._validate_answers(request, questions, options_by_question)
        correct_count = 0
        stored: list[StudentAnswer] = []
        for question in questions:
            option_id = selected.get(question.id)
            correct = option_id is not None and any(
                option.id == option_id and option.is_correct
                for option in options_by_question.get(question.id, [])
            )
            if correct:
                correct_count += 1
            stored.append(
                StudentAnswer(
                    attempt_id=attempt.id,
                    question_id=question.id,
                    selected_option_id=option_id,
                    is_correct=correct,
                )
            )
        self._session.add_all(stored)
        self._session.flush()

        now = utcnow()
        attempt.status = AttemptStatus.SUBMITTED.value
        attempt.total_questions = len(questions)
        attempt.correct_count = correct_count
        attempt.score = (
            Decimal(correct_count) * Decimal(100) / Decimal(len(questions))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        attempt.submitted_at = now
        self._session.flush()
        return self._to_result(attempt, quiz, questions, options_by_question, stored)

    # --------------------------------------------------------------------- get
    def get(self, attempt_id: int, actor: AuthenticatedUser) -> dict:
        student = self._current_student(actor)
        attempt = self._session.get(QuizAttempt, attempt_id)
        if attempt is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Attempt not found")
        self._require_owner(attempt, student.user_id)
        if attempt.status == AttemptStatus.IN_PROGRESS.value:
            return _to_attempt(attempt).model_dump(mode="json")

        quiz = self._session.get(Quiz, attempt.quiz_id)
        if quiz is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Quiz not found")
        questions = self._questions(quiz.id)
        result = self._stored_result(attempt, quiz, questions, self._load_options(questions))
        return result.model_dump(mode="json")

    # --------------------------------------------------------------- internals
    def _stored_result(
        self,
        attempt: QuizAttempt,
        quiz: Quiz,
        questions: list[Question],
        options_by_question: dict[int, list[QuestionOption]],
    ) -> AttemptResultResponse:
        answers = list(
            self._session.scalars(
                select(StudentAnswer)
                .where(StudentAnswer.attempt_id == attempt.id)
                .order_by(StudentAnswer.question_id.asc())
            ).all()
        )
        return self._to_result(attempt, quiz, questions, options_by_question, answers)

    def _validate_answers(
        self,
        request: SubmitAttemptRequest,
        questions: list[Question],
        options_by_question: dict[int, list[QuestionOption]],
    ) -> dict[int, int | None]:
        known = {question.id for question in questions}
        selected: dict[int, int | None] = {}
        seen: set[int] = set()
        for answer in request.answers:
            question_id = int(answer.question_id)
            if question_id in seen:
                raise ApiException(ErrorCode.INVALID_ANSWER, "Duplicate question_id")
            seen.add(question_id)
            if question_id not in known:
                raise ApiException(
                    ErrorCode.INVALID_ANSWER, "Question does not belong to the attempt quiz"
                )
            option_id = (
                None if answer.selected_option_id is None else int(answer.selected_option_id)
            )
            if option_id is not None and not any(
                option.id == option_id for option in options_by_question.get(question_id, [])
            ):
                raise ApiException(
                    ErrorCode.INVALID_ANSWER, "Option does not belong to the question"
                )
            selected[question_id] = option_id
        return selected

    def _to_result(
        self,
        attempt: QuizAttempt,
        quiz: Quiz,
        questions: list[Question],
        options_by_question: dict[int, list[QuestionOption]],
        answers: list[StudentAnswer],
    ) -> AttemptResultResponse:
        by_question = {answer.question_id: answer for answer in answers}
        review: list[ReviewItem] = []
        for question in questions:
            options = sorted(
                options_by_question.get(question.id, []), key=lambda item: item.order_index
            )
            correct = next((option for option in options if option.is_correct), None)
            if correct is None:
                raise ApiException(ErrorCode.INVALID_STATE, "Question has no correct option")
            answer = by_question.get(question.id)
            review.append(
                ReviewItem(
                    question_id=str(question.id),
                    question_content=question.content,
                    selected_option_id=(
                        None
                        if answer is None or answer.selected_option_id is None
                        else str(answer.selected_option_id)
                    ),
                    is_correct=bool(answer is not None and answer.is_correct),
                    correct_option_id=str(correct.id),
                    explanation=question.explanation,
                    options=[
                        ReviewOption(id=str(option.id), content=option.content)
                        for option in options
                    ],
                )
            )
        return AttemptResultResponse(
            id=str(attempt.id),
            quiz_id=str(quiz.id),
            quiz_title=quiz.title,
            student_id=str(attempt.student_id),
            status=AttemptStatus(attempt.status),
            score=attempt.score,
            total_questions=attempt.total_questions,
            correct_count=attempt.correct_count,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
            review=review,
        )

    def _load_options(self, questions: list[Question]) -> dict[int, list[QuestionOption]]:
        grouped: dict[int, list[QuestionOption]] = {question.id: [] for question in questions}
        if not questions:
            return grouped
        rows = self._session.scalars(
            select(QuestionOption)
            .where(QuestionOption.question_id.in_([question.id for question in questions]))
            .order_by(QuestionOption.order_index.asc())
        ).all()
        for option in rows:
            grouped.setdefault(option.question_id, []).append(option)
        return grouped

    def _questions(self, quiz_id: int) -> list[Question]:
        return list(
            self._session.scalars(
                select(Question)
                .where(Question.quiz_id == quiz_id)
                .order_by(Question.order_index.asc())
            ).all()
        )

    def _question_count(self, quiz_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(Question).where(Question.quiz_id == quiz_id)
            )
            or 0
        )

    def _owned_attempt_for_update(self, attempt_id: int, student_id: int) -> QuizAttempt:
        attempt = self._session.scalars(
            select(QuizAttempt).where(QuizAttempt.id == attempt_id).with_for_update()
        ).first()
        if attempt is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Attempt not found")
        self._require_owner(attempt, student_id)
        return attempt

    @staticmethod
    def _require_owner(attempt: QuizAttempt, student_id: int) -> None:
        if attempt.student_id != student_id:
            raise ApiException(ErrorCode.NOT_FOUND, "Attempt not found")

    @staticmethod
    def _current_student(actor: AuthenticatedUser) -> AuthenticatedUser:
        if actor.role is not UserRole.STUDENT:
            raise ApiException(ErrorCode.FORBIDDEN)
        return actor

    def _lesson_course_id(self, lesson_id: int) -> int | None:
        return self._session.scalar(select(Lesson.course_id).where(Lesson.id == lesson_id))

    def _is_enrolled(self, course_id: int, student_id: int) -> bool:
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


def _to_attempt(attempt: QuizAttempt) -> AttemptResponse:
    return AttemptResponse(
        id=str(attempt.id),
        quiz_id=str(attempt.quiz_id),
        student_id=str(attempt.student_id),
        status=AttemptStatus(attempt.status),
        total_questions=attempt.total_questions,
        started_at=attempt.started_at,
    )
