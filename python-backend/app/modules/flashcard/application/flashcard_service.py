
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.ai.application.generation_service import AiGenerationService
from app.modules.flashcard.api.schemas import (
    CardResponse,
    CardUpdateRequest,
    CardWriteRequest,
    card_response,
)
from app.modules.lesson.application.access_policy import (
    LessonAccessPolicy,
    LessonViewAccess,
)
from app.shared.database.base import utcnow
from app.shared.database.models import Flashcard
from app.shared.domain.enums import FlashcardStatus, GenerationType
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.pagination import page_response


class FlashcardService:
    def __init__(
        self,
        session: Session,
        policy: LessonAccessPolicy,
        ai_generation: AiGenerationService,
    ) -> None:
        self._session = session
        self._policy = policy
        self._ai = ai_generation

    def list_flashcards(
        self, lesson_id: int, user_id: int, page: int, page_size: int
    ) -> dict:
        if page < 1:
            raise ApiException.field_error("page", "page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise ApiException.field_error("page_size", "page_size must be between 1 and 100")

        access = self._policy.assert_can_view_lesson(lesson_id, user_id)
        statement = select(Flashcard).where(Flashcard.lesson_id == lesson_id)
        count_statement = (
            select(func.count()).select_from(Flashcard).where(Flashcard.lesson_id == lesson_id)
        )
        if access is not LessonViewAccess.MANAGER:
            published = FlashcardStatus.PUBLISHED.value
            statement = statement.where(Flashcard.status == published)
            count_statement = count_statement.where(Flashcard.status == published)

        total = self._session.scalar(count_statement) or 0
        rows = self._session.scalars(
            statement.order_by(Flashcard.created_at.desc(), Flashcard.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return page_response([card_response(row) for row in rows], page, page_size, total)

    def save_draft(
        self, lesson_id: int, teacher_id: int, request: CardWriteRequest
    ) -> CardResponse:
        self._policy.assert_can_manage_lesson(lesson_id, teacher_id)
        generated_by_ai = False
        if request.generation_id is not None:
            self._ai.validate_for_save(
                request.generation_id, lesson_id, teacher_id, GenerationType.FLASHCARD
            )
            generated_by_ai = True

        now = utcnow()
        card = Flashcard(
            lesson_id=lesson_id,
            front_text=request.front_text.strip(),
            back_text=request.back_text.strip(),
            status=FlashcardStatus.DRAFT.value,
            generated_by_ai=generated_by_ai,
            generation_id=request.generation_id,
            created_by=teacher_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(card)
        self._session.flush()
        return card_response(card)

    def update_draft(
        self, card_id: int, teacher_id: int, request: CardUpdateRequest
    ) -> CardResponse:
        card = self._load_managed_draft(card_id, teacher_id)
        if request.front_text is not None:
            card.front_text = request.front_text.strip()
        if request.back_text is not None:
            card.back_text = request.back_text.strip()
        card.updated_at = utcnow()
        self._session.flush()
        return card_response(card)

    def delete_draft(self, card_id: int, teacher_id: int) -> None:
        card = self._load_managed_draft(card_id, teacher_id)
        self._session.delete(card)
        self._session.flush()

    def change_status(
        self, card_id: int, teacher_id: int, target: FlashcardStatus
    ) -> CardResponse:
        if target is FlashcardStatus.PUBLISHED:
            return self.publish(card_id, teacher_id)
        if target is FlashcardStatus.CLOSED:
            return self.close(card_id, teacher_id)
        raise ApiException.field_error("status", "status must be PUBLISHED or CLOSED")

    def publish(self, card_id: int, teacher_id: int) -> CardResponse:
        card = self._load_managed(card_id, teacher_id)
        if card.status == FlashcardStatus.PUBLISHED.value:
            return card_response(card)
        if card.status != FlashcardStatus.DRAFT.value:
            raise ApiException(
                ErrorCode.INVALID_STATE, "Only a draft flashcard can be published"
            )
        if not card.front_text.strip() or not card.back_text.strip():
            raise ApiException(
                ErrorCode.INVALID_STATE, "Front and back text must not be empty"
            )
        now = utcnow()
        card.status = FlashcardStatus.PUBLISHED.value
        card.published_at = now
        card.updated_at = now
        self._session.flush()
        return card_response(card)

    def close(self, card_id: int, teacher_id: int) -> CardResponse:
        card = self._load_managed(card_id, teacher_id)
        if card.status == FlashcardStatus.CLOSED.value:
            return card_response(card)
        if card.status != FlashcardStatus.PUBLISHED.value:
            raise ApiException(
                ErrorCode.INVALID_STATE, "Only a published flashcard can be closed"
            )
        now = utcnow()
        card.status = FlashcardStatus.CLOSED.value
        card.closed_at = now
        card.updated_at = now
        self._session.flush()
        return card_response(card)

    def _load_managed(self, card_id: int, teacher_id: int) -> Flashcard:
        card = self._session.get(Flashcard, card_id)
        if card is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Flashcard not found")
        self._policy.assert_can_manage_lesson(card.lesson_id, teacher_id)
        return card

    def _load_managed_draft(self, card_id: int, teacher_id: int) -> Flashcard:
        card = self._load_managed(card_id, teacher_id)
        if card.status != FlashcardStatus.DRAFT.value:
            raise ApiException(
                ErrorCode.INVALID_STATE, "Only a draft flashcard can be changed"
            )
        return card
