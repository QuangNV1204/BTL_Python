
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.assessment.api.schemas import (
    CreateQuizRequest,
    OptionWrite,
    QuizAuthorResponse,
    QuizPublicationRequest,
    QuizStudentResponse,
    QuizSummaryResponse,
    UpdateQuizRequest,
    WriteQuestionRequest,
    quiz_author_response,
    quiz_student_response,
)
from app.modules.lesson.application.access_policy import LessonAccessPolicy
from app.shared.auth.principal import AuthenticatedUser
from app.shared.database.base import utcnow
from app.shared.database.models import (
    AIGeneration,
    Question,
    QuestionOption,
    Quiz,
    QuizAttempt,
)
from app.shared.domain.enums import GenerationStatus, QuizStatus, UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.pagination import page_response

logger = logging.getLogger("learningai.quiz")


class QuizService:
    def __init__(self, session: Session, policy: LessonAccessPolicy) -> None:
        self._session = session
        self._policy = policy


    def create(self, lesson_id: int, request: CreateQuizRequest, actor: AuthenticatedUser) -> QuizAuthorResponse:
        lesson = self._policy.lesson_context(lesson_id)
        if not self._is_manager(actor, lesson.course_id):
            raise ApiException(ErrorCode.FORBIDDEN)
        if request.generation_id is not None:
            self._validate_generation(request.generation_id, lesson_id, actor.user_id)

        now = utcnow()
        quiz = Quiz(
            lesson_id=lesson_id,
            title=request.title,
            status=QuizStatus.DRAFT.value,
            generation_id=request.generation_id,
            created_by=actor.user_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(quiz)
        self._session.flush()
        return quiz_author_response(quiz, [], {})

    def list(self, lesson_id: int, actor: AuthenticatedUser, page: int, page_size: int) -> dict:
        if page < 1 or page_size < 1 or page_size > 100:
            raise ApiException(ErrorCode.VALIDATION_ERROR, "Invalid pagination")

        lesson = self._policy.lesson_context(lesson_id)
        manager = self._is_manager(actor, lesson.course_id)
        if not manager:
            self._require_enrollment(actor, lesson.course_id)

        statement = select(Quiz).where(Quiz.lesson_id == lesson_id)
        count_statement = select(func.count()).select_from(Quiz).where(Quiz.lesson_id == lesson_id)
        if not manager:
            statement = statement.where(Quiz.status == QuizStatus.PUBLISHED.value)
            count_statement = count_statement.where(Quiz.status == QuizStatus.PUBLISHED.value)

        total = self._session.scalar(count_statement) or 0
        quizzes = list(
            self._session.scalars(
                statement.order_by(Quiz.created_at.desc(), Quiz.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        counts = self._question_counts([quiz.id for quiz in quizzes])
        items = [
            QuizSummaryResponse(
                id=str(quiz.id),
                lesson_id=str(quiz.lesson_id),
                title=quiz.title,
                status=QuizStatus(quiz.status),
                question_count=counts.get(quiz.id, 0),
            )
            for quiz in quizzes
        ]
        return page_response(items, page, page_size, total)

    def get(self, quiz_id: int, actor: AuthenticatedUser) -> QuizAuthorResponse | QuizStudentResponse:
        quiz = self._quiz(quiz_id)
        lesson = self._policy.lesson_context(quiz.lesson_id)
        manager = self._is_manager(actor, lesson.course_id)
        if not manager:
            if actor.role is UserRole.STUDENT and quiz.status != QuizStatus.PUBLISHED.value and not (
                quiz.status == QuizStatus.CLOSED.value
                and self._has_in_progress_attempt(quiz_id, actor.user_id)
            ):
                raise ApiException(ErrorCode.NOT_FOUND, "Quiz not found")
            self._require_enrollment(actor, lesson.course_id)

        questions = self._questions(quiz_id)
        options = self._load_options(questions)
        if manager:
            return quiz_author_response(quiz, questions, options)
        return quiz_student_response(quiz, questions, options)


    def update(self, quiz_id: int, request: UpdateQuizRequest, actor: AuthenticatedUser) -> QuizAuthorResponse:
        quiz = self._managed_draft(quiz_id, actor)
        if request.generation_id is not None:
            self._validate_generation(request.generation_id, quiz.lesson_id, actor.user_id)
        if request.title is not None:
            quiz.title = request.title
        if request.generation_id is not None:
            quiz.generation_id = request.generation_id
        quiz.updated_at = utcnow()
        self._session.flush()

        questions = self._questions(quiz_id)
        return quiz_author_response(quiz, questions, self._load_options(questions))

    def delete(self, quiz_id: int, actor: AuthenticatedUser) -> None:
        quiz = self._managed_draft(quiz_id, actor)
        self._require_no_history(quiz_id)
        questions = self._questions(quiz_id)
        try:
            for question in questions:
                self._delete_options(question.id)
            for question in questions:
                self._session.delete(question)
            self._session.flush()
            self._session.delete(quiz)
            self._session.flush()
        except IntegrityError as exc:
            if _is_foreign_key_error(exc):
                raise ApiException(
                    ErrorCode.RESOURCE_IN_USE, "Quiz content is referenced by learning history"
                ) from exc
            raise


    def add_question(self, quiz_id: int, request: WriteQuestionRequest, actor: AuthenticatedUser):
        quiz = self._managed_draft(quiz_id, actor)
        self._require_no_history(quiz_id)
        request.validate_rules()
        if self._order_index_exists(quiz_id, request.order_index, exclude_id=None):
            raise ApiException(ErrorCode.INVALID_STATE, "Question order_index already exists")
        if request.generation_id is not None:
            self._validate_generation(request.generation_id, quiz.lesson_id, actor.user_id)

        now = utcnow()
        question = Question(
            quiz_id=quiz_id,
            question_type="MULTIPLE_CHOICE",
            created_at=now,
        )
        self._apply_question(question, request)
        self._session.add(question)
        self._session.flush()
        options = self._save_options(question.id, request)
        return _question_author(question, options)

    def replace_question(
        self, question_id: int, request: WriteQuestionRequest, actor: AuthenticatedUser
    ):
        quiz_id = self._quiz_id_of_question(question_id)
        quiz = self._managed_draft(quiz_id, actor)
        question = self._session.scalars(
            select(Question)
            .where(Question.id == question_id, Question.quiz_id == quiz_id)
            .with_for_update()
        ).first()
        if question is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Question not found")

        self._require_no_history(quiz_id)
        request.validate_rules()
        if self._order_index_exists(quiz_id, request.order_index, exclude_id=question_id):
            raise ApiException(ErrorCode.INVALID_STATE, "Question order_index already exists")
        if request.generation_id is not None:
            self._validate_generation(request.generation_id, quiz.lesson_id, actor.user_id)

        self._apply_question(question, request)
        self._delete_options(question_id)
        self._session.flush()
        options = self._save_options(question_id, request)
        return _question_author(question, options)

    def delete_question(self, question_id: int, actor: AuthenticatedUser) -> None:
        quiz_id = self._quiz_id_of_question(question_id)
        self._managed_draft(quiz_id, actor)
        question = self._session.scalars(
            select(Question)
            .where(Question.id == question_id, Question.quiz_id == quiz_id)
            .with_for_update()
        ).first()
        if question is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Question not found")
        self._require_no_history(quiz_id)
        self._delete_options(question_id)
        self._session.flush()
        self._session.delete(question)
        self._session.flush()


    def change_publication(
        self, quiz_id: int, request: QuizPublicationRequest, actor: AuthenticatedUser
    ) -> QuizAuthorResponse:
        quiz = self._managed_quiz(quiz_id, actor)
        target = request.status
        publishing = quiz.status == QuizStatus.DRAFT.value and target is QuizStatus.PUBLISHED
        closing = quiz.status == QuizStatus.PUBLISHED.value and target is QuizStatus.CLOSED
        if not publishing and not closing:
            raise ApiException(
                ErrorCode.INVALID_STATE,
                "Only DRAFT to PUBLISHED or PUBLISHED to CLOSED is allowed",
            )

        questions = self._questions(quiz_id)
        options = self._load_options(questions)
        now = utcnow()
        if publishing:
            self._require_no_history(quiz_id)
            self._validate_for_publication(quiz, questions, options)
            quiz.published_at = now
        else:
            quiz.closed_at = now
        quiz.status = target.value
        quiz.updated_at = now
        self._session.flush()
        return quiz_author_response(quiz, questions, options)


    def _quiz(self, quiz_id: int) -> Quiz:
        quiz = self._session.get(Quiz, quiz_id)
        if quiz is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Quiz not found")
        return quiz

    def _managed_quiz(self, quiz_id: int, actor: AuthenticatedUser) -> Quiz:
        quiz = self._session.scalars(
            select(Quiz).where(Quiz.id == quiz_id).with_for_update()
        ).first()
        if quiz is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Quiz not found")
        lesson = self._policy.lesson_context(quiz.lesson_id)
        if not self._is_manager(actor, lesson.course_id):
            raise ApiException(ErrorCode.FORBIDDEN)
        return quiz

    def _managed_draft(self, quiz_id: int, actor: AuthenticatedUser) -> Quiz:
        quiz = self._managed_quiz(quiz_id, actor)
        if quiz.status != QuizStatus.DRAFT.value:
            raise ApiException(ErrorCode.INVALID_STATE, "Only DRAFT quizzes can be changed")
        return quiz

    def _is_manager(self, actor: AuthenticatedUser, course_id: int) -> bool:
        if actor.is_admin:
            return True
        return actor.role is UserRole.TEACHER and self._policy.course_teacher_id(course_id) == actor.user_id

    def _require_enrollment(self, actor: AuthenticatedUser, course_id: int) -> None:
        if actor.role is not UserRole.STUDENT:
            raise ApiException(ErrorCode.FORBIDDEN)
        if not self._policy.is_enrolled(course_id, actor.user_id):
            raise ApiException(ErrorCode.ENROLLMENT_REQUIRED)

    def _require_no_history(self, quiz_id: int) -> None:
        if self._has_learning_history(quiz_id):
            raise ApiException(ErrorCode.RESOURCE_IN_USE, "Quiz has learning history")

    def _has_learning_history(self, quiz_id: int) -> bool:
        attempt = self._session.scalar(
            select(func.count())
            .select_from(QuizAttempt)
            .where(QuizAttempt.quiz_id == quiz_id)
        )
        if attempt:
            return True
        from app.shared.database.models import StudentAnswer

        answer = self._session.scalar(
            select(func.count())
            .select_from(StudentAnswer)
            .join(Question, Question.id == StudentAnswer.question_id)
            .where(Question.quiz_id == quiz_id)
        )
        if answer:
            return True
        selected = self._session.scalar(
            select(func.count())
            .select_from(StudentAnswer)
            .join(QuestionOption, QuestionOption.id == StudentAnswer.selected_option_id)
            .join(Question, Question.id == QuestionOption.question_id)
            .where(Question.quiz_id == quiz_id)
        )
        return bool(selected)

    def _has_in_progress_attempt(self, quiz_id: int, student_id: int) -> bool:
        return bool(
            self._session.scalar(
                select(func.count())
                .select_from(QuizAttempt)
                .where(
                    QuizAttempt.quiz_id == quiz_id,
                    QuizAttempt.student_id == student_id,
                    QuizAttempt.status == "IN_PROGRESS",
                )
            )
        )

    def _questions(self, quiz_id: int) -> list[Question]:
        return list(
            self._session.scalars(
                select(Question)
                .where(Question.quiz_id == quiz_id)
                .order_by(Question.order_index.asc())
            ).all()
        )

    def _load_options(self, questions: list[Question]) -> dict[int, list[QuestionOption]]:
        grouped: dict[int, list[QuestionOption]] = {question.id: [] for question in questions}
        if not questions:
            return grouped
        rows = self._session.scalars(
            select(QuestionOption).where(
                QuestionOption.question_id.in_([question.id for question in questions])
            )
        ).all()
        for option in rows:
            grouped.setdefault(option.question_id, []).append(option)
        return grouped

    def _question_counts(self, quiz_ids: list[int]) -> dict[int, int]:
        if not quiz_ids:
            return {}
        rows = self._session.execute(
            select(Question.quiz_id, func.count())
            .where(Question.quiz_id.in_(quiz_ids))
            .group_by(Question.quiz_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows}

    def _quiz_id_of_question(self, question_id: int) -> int:
        quiz_id = self._session.scalar(
            select(Question.quiz_id).where(Question.id == question_id)
        )
        if quiz_id is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Question not found")
        return quiz_id

    def _order_index_exists(self, quiz_id: int, order_index: int, exclude_id: int | None) -> bool:
        statement = select(func.count()).select_from(Question).where(
            Question.quiz_id == quiz_id, Question.order_index == order_index
        )
        if exclude_id is not None:
            statement = statement.where(Question.id != exclude_id)
        return bool(self._session.scalar(statement))

    def _apply_question(self, question: Question, request: WriteQuestionRequest) -> None:
        question.content = request.content
        question.explanation = request.explanation
        question.order_index = request.order_index
        if request.generation_id is not None:
            question.generation_id = request.generation_id
        question.generated_by_ai = question.generation_id is not None

    def _save_options(self, question_id: int, request: WriteQuestionRequest) -> list[QuestionOption]:
        options = [
            QuestionOption(
                question_id=question_id,
                content=option.content,
                is_correct=option.is_correct,
                order_index=option.order_index,
            )
            for option in request.options
        ]
        self._session.add_all(options)
        self._session.flush()
        return options

    def _delete_options(self, question_id: int) -> None:
        for option in self._session.scalars(
            select(QuestionOption).where(QuestionOption.question_id == question_id)
        ).all():
            self._session.delete(option)

    def _validate_generation(self, generation_id: int, lesson_id: int, user_id: int) -> None:
        generation = self._session.get(AIGeneration, generation_id)
        if generation is None:
            raise ApiException(ErrorCode.VALIDATION_ERROR, "Generation not found")
        if generation.created_by != user_id:
            raise ApiException(ErrorCode.FORBIDDEN, "Generation belongs to another user")
        if (
            generation.lesson_id != lesson_id
            or generation.generation_type != "QUIZ"
            or generation.status != GenerationStatus.SUCCEEDED.value
        ):
            raise ApiException(
                ErrorCode.VALIDATION_ERROR,
                "Generation is not a successful quiz generation for this lesson",
            )

    def _validate_for_publication(self, quiz: Quiz, questions: list[Question],
                                  options: dict[int, list[QuestionOption]]) -> None:
        if (
            quiz.title is None
            or not quiz.title.strip()
            or len(quiz.title) > 200
            or not questions
        ):
            raise ApiException(ErrorCode.INVALID_QUIZ)
        positions: set[int] = set()
        for question in questions:
            if question.question_type != "MULTIPLE_CHOICE" or question.order_index in positions:
                raise ApiException(ErrorCode.INVALID_QUIZ)
            positions.add(question.order_index)
            values = [
                OptionWrite(
                    content=option.content,
                    is_correct=bool(option.is_correct),
                    order_index=option.order_index,
                )
                for option in options.get(question.id, [])
            ]
            try:
                WriteQuestionRequest(
                    content=question.content,
                    explanation=question.explanation,
                    order_index=question.order_index,
                    options=values,
                    generation_id=question.generation_id,
                ).validate_rules()
            except ApiException as exc:
                raise ApiException(ErrorCode.INVALID_QUIZ, exc.message) from exc


def _question_author(question: Question, options: list[QuestionOption]):
    from app.modules.assessment.api.schemas import OptionAuthor, QuestionAuthor

    return QuestionAuthor(
        id=str(question.id),
        content=question.content,
        explanation=question.explanation,
        order_index=question.order_index,
        generated_by_ai=bool(question.generated_by_ai),
        options=[
            OptionAuthor(
                id=str(option.id),
                content=option.content,
                is_correct=bool(option.is_correct),
                order_index=option.order_index,
            )
            for option in sorted(options, key=lambda item: item.order_index)
        ],
    )


def _is_foreign_key_error(exc: IntegrityError) -> bool:
    args = getattr(exc.orig, "args", ())
    return bool(args) and args[0] == 1451
