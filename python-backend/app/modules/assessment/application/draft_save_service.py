"""Lưu toàn bộ draft quiz có idempotency — sao QuizDraftSaveService.java.

Receipt ``quiz_draft_save_receipts`` (V9) ghi theo (quiz_id, actor_id, request_id):
gọi lại cùng request_id + cùng payload trả nguyên response cũ; khác payload → 409.
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.assessment.api.schemas import (
    QuizAuthorResponse,
    SaveQuizDraftRequest,
    UpdateQuizRequest,
)
from app.modules.assessment.application.quiz_service import QuizService
from app.shared.auth.principal import AuthenticatedUser
from app.shared.database.base import utcnow
from app.shared.database.models import Question, Quiz
from app.shared.domain.enums import QuizStatus, UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException

logger = logging.getLogger("learningai.quiz")


class QuizDraftSaveService:
    def __init__(self, session: Session, quiz_service: QuizService) -> None:
        self._session = session
        self._quizzes = quiz_service

    def save(
        self, quiz_id: int, request: SaveQuizDraftRequest, actor: AuthenticatedUser
    ) -> QuizAuthorResponse:
        quiz = self._session.scalars(
            select(Quiz).where(Quiz.id == quiz_id).with_for_update()
        ).first()
        if quiz is None:
            raise ApiException(ErrorCode.NOT_FOUND)

        teacher_id = self._course_teacher_id(quiz.lesson_id)
        if teacher_id is None:
            raise ApiException(ErrorCode.NOT_FOUND)
        if not actor.is_admin and not (
            actor.role is UserRole.TEACHER and actor.user_id == teacher_id
        ):
            raise ApiException(ErrorCode.FORBIDDEN)

        payload_hash = _sha256(_canonical_request(request))
        receipt = self._session.execute(
            text(
                "SELECT payload_hash, response_json FROM quiz_draft_save_receipts "
                "WHERE quiz_id = :quiz AND actor_id = :actor AND request_id = :request"
            ),
            {"quiz": quiz_id, "actor": actor.user_id, "request": request.request_id},
        ).first()
        if receipt is not None:
            if receipt.payload_hash != payload_hash:
                raise ApiException(
                    ErrorCode.INVALID_STATE,
                    "request_id was already used with a different payload",
                )
            return QuizAuthorResponse.model_validate(json.loads(receipt.response_json))

        if quiz.status != QuizStatus.DRAFT.value:
            raise ApiException(ErrorCode.INVALID_STATE, "Only DRAFT quizzes can be changed")
        if self._quizzes._has_learning_history(quiz_id):  # noqa: SLF001 - cùng module
            raise ApiException(ErrorCode.RESOURCE_IN_USE, "Quiz has learning history")

        current = self._quizzes._questions(quiz_id)  # noqa: SLF001
        existing_ids = {question.id for question in current}
        wanted: set[int] = set()
        for item in request.questions:
            item.question.validate_rules()
            if item.id is not None:
                if item.id not in existing_ids or item.id in wanted:
                    raise ApiException(
                        ErrorCode.VALIDATION_ERROR,
                        "Question id must belong to this quiz and occur once",
                    )
                wanted.add(item.id)

        # Dùng lại validate ownership/history/provenance của QuizService trong cùng transaction.
        for question in current:
            if question.id not in wanted:
                self._quizzes.delete_question(question.id, actor)

        # Đẩy câu giữ lại ra ngoài khoảng để nhường order_index cho payload mới.
        base = (
            max(
                max((question.order_index for question in current), default=-1),
                len(request.questions),
            )
            + 1
        )
        if base + len(current) > 2**31 - 1:
            raise ApiException(ErrorCode.INVALID_STATE, "Question order limit exceeded")
        position = 0
        kept = [question for question in current if question.id in wanted]
        for question in sorted(kept, key=lambda item: item.order_index):
            question.order_index = base + position
            position += 1
        self._session.flush()

        self._quizzes.update(quiz_id, UpdateQuizRequest(title=request.title), actor)
        for item in request.questions:
            if item.id is None:
                self._quizzes.add_question(quiz_id, item.question, actor)
            else:
                self._quizzes.replace_question(item.id, item.question, actor)

        result = self._quizzes.get(quiz_id, actor)
        assert isinstance(result, QuizAuthorResponse)

        self._session.execute(
            text(
                "INSERT INTO quiz_draft_save_receipts"
                "(quiz_id, actor_id, request_id, payload_hash, response_json, created_at) "
                "VALUES (:quiz, :actor, :request, :hash, :response, :created)"
            ),
            {
                "quiz": quiz_id,
                "actor": actor.user_id,
                "request": request.request_id,
                "hash": payload_hash,
                "response": json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
                "created": utcnow(),
            },
        )
        return result

    def _course_teacher_id(self, lesson_id: int) -> int | None:
        return self._quizzes._policy.course_teacher_id(  # noqa: SLF001
            self._quizzes._policy.lesson_context(lesson_id).course_id  # noqa: SLF001
        )


def _canonical_request(request: SaveQuizDraftRequest) -> str:
    """Hash payload ổn định: đúng các field đã parse, không phụ thuộc thứ tự dict."""
    payload = {
        "request_id": request.request_id,
        "title": request.title,
        "questions": [
            {
                "id": item.id,
                "content": item.question.content,
                "explanation": item.question.explanation,
                "order_index": item.question.order_index,
                "generation_id": item.question.generation_id,
                "options": [
                    {
                        "content": option.content,
                        "is_correct": option.is_correct,
                        "order_index": option.order_index,
                    }
                    for option in item.question.options
                ],
            }
            for item in request.questions
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["QuizDraftSaveService", "Question"]
