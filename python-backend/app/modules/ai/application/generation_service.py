"""Sinh quiz/flashcard bằng AI — sao AiGenerationService.java.

Chỉ trả preview candidate, không tạo quiz/card. Gọi AI ngoài transaction; mỗi lần
sinh (thành công hay lỗi) lưu một bản ghi ``ai_generations`` để tra vết.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.modules.ai.domain.candidate_validator import (
    parse_card_candidate,
    parse_quiz_candidate,
)
from app.modules.ai.domain.contracts import (
    AIClient,
    AIClientException,
    AiFailureReason,
    CardCandidate,
    FlashcardCandidate,
    QuestionCandidate,
    QuizCandidate,
)
from app.modules.ai.infrastructure.prompts import (
    FLASHCARD_PROMPT_VERSION,
    QUIZ_PROMPT_VERSION,
    build_flashcard_prompt,
    build_quiz_prompt,
)
from app.modules.lesson.application.access_policy import LessonAccessPolicy
from app.modules.lesson.application.lesson_service import LessonService
from app.shared.config.settings import Settings
from app.shared.database.base import utcnow
from app.shared.database.models import AIGeneration
from app.shared.domain.enums import (
    Difficulty,
    GenerationStatus,
    GenerationType,
    SourceType,
)
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException, InvalidCandidateException


@dataclass(frozen=True)
class GenerationRequest:
    lesson_id: int
    source_type: SourceType
    document_id: int | None
    count: int
    difficulty: Difficulty | None


@dataclass
class _Generated:
    generation: AIGeneration
    candidate: list
    source_truncated: bool


_FAILURE_BY_REASON = {
    AiFailureReason.TIMEOUT: ErrorCode.AI_TIMEOUT,
    AiFailureReason.PROVIDER_ERROR: ErrorCode.AI_PROVIDER_ERROR,
    AiFailureReason.INVALID_OUTPUT: ErrorCode.AI_OUTPUT_INVALID,
}

logger = logging.getLogger("learningai.ai")


class AiGenerationService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        ai_client: AIClient,
        policy: LessonAccessPolicy,
        lesson_service: LessonService,
    ) -> None:
        self._session = session
        self._settings = settings
        self._ai = ai_client
        self._policy = policy
        self._lessons = lesson_service

    # ----------------------------------------------------------------- public
    def generate_quiz(self, teacher_id: int, request: GenerationRequest) -> dict:
        if request.difficulty is None:
            raise ApiException.field_error(
                "difficulty", "difficulty is required for quiz generation"
            )
        result = self._generate(
            teacher_id,
            request,
            GenerationType.QUIZ,
            QUIZ_PROMPT_VERSION,
            lambda text: build_quiz_prompt(text, request.count, request.difficulty),
            lambda raw: parse_quiz_candidate(raw, request.count),
            lambda candidate: QuizCandidate(candidate),
        )
        return {
            "generation_id": str(result.generation.id),
            "lesson_id": str(request.lesson_id),
            "source_truncated": result.source_truncated,
            "candidate": {"questions": _questions_json(result.candidate)},
        }

    def generate_flashcards(self, teacher_id: int, request: GenerationRequest) -> dict:
        result = self._generate(
            teacher_id,
            request,
            GenerationType.FLASHCARD,
            FLASHCARD_PROMPT_VERSION,
            lambda text: build_flashcard_prompt(text, request.count),
            lambda raw: parse_card_candidate(raw, request.count),
            lambda candidate: FlashcardCandidate(candidate),
        )
        return {
            "generation_id": str(result.generation.id),
            "lesson_id": str(request.lesson_id),
            "source_truncated": result.source_truncated,
            "candidate": {"flashcards": _cards_json(result.candidate)},
        }

    def validate_for_save(
        self, generation_id: int, lesson_id: int, teacher_id: int, generation_type: GenerationType
    ) -> AIGeneration:
        """Kiểm tra generation_id trước khi lưu Draft (Quiz/Flashcard service gọi)."""
        generation = self._session.get(AIGeneration, generation_id)
        if generation is None:
            raise ApiException.field_error("generation_id", "generation not found")
        if generation.created_by != teacher_id:
            raise ApiException(ErrorCode.FORBIDDEN, "Generation belongs to another user")
        if generation.lesson_id != lesson_id:
            raise ApiException.field_error(
                "generation_id", "generation belongs to another lesson"
            )
        if generation.generation_type != generation_type.value:
            raise ApiException.field_error(
                "generation_id", f"generation type is not {generation_type.value}"
            )
        if generation.status != GenerationStatus.SUCCEEDED.value:
            raise ApiException.field_error("generation_id", "generation did not succeed")
        return generation

    # -------------------------------------------------------------- internals
    def _generate(
        self,
        teacher_id: int,
        request: GenerationRequest,
        generation_type: GenerationType,
        prompt_version: str,
        prompt_factory,
        validator,
        to_stored,
    ) -> _Generated:
        document_id = _check_source(request)
        self._policy.assert_can_manage_lesson(request.lesson_id, teacher_id)

        source = self._lessons.get_source_text(
            request.lesson_id, request.source_type, document_id
        )
        limit = self._settings.ai_max_source_chars_effective
        truncated = len(source) > limit
        sent_text = source[:limit] if truncated else source

        generation = AIGeneration(
            lesson_id=request.lesson_id,
            source_document_id=document_id,
            source_type=request.source_type.value,
            generation_type=generation_type.value,
            requested_count=request.count,
            difficulty=request.difficulty.value
            if generation_type is GenerationType.QUIZ and request.difficulty
            else None,
            provider=self._ai.provider(),
            model=self._ai.model(),
            prompt_version=prompt_version,
            source_hash=hashlib.sha256(sent_text.encode("utf-8")).hexdigest(),
            status=GenerationStatus.FAILED.value,
            created_by=teacher_id,
            created_at=utcnow(),
        )

        try:
            raw = self._ai.generate(prompt_factory(sent_text))
        except AIClientException as exc:
            code = _FAILURE_BY_REASON[exc.reason]
            self._save_failed(generation, code)
            logger.warning(
                "AI generation failed for lesson %s: %s (%s)",
                request.lesson_id,
                code.value,
                exc,
            )
            raise ApiException.of(code) from exc

        try:
            candidate = validator(raw)
        except InvalidCandidateException as exc:
            self._save_failed(generation, ErrorCode.AI_OUTPUT_INVALID)
            logger.warning(
                "AI output invalid for lesson %s: %s", request.lesson_id, exc
            )
            raise ApiException.of(ErrorCode.AI_OUTPUT_INVALID) from exc

        generation.status = GenerationStatus.SUCCEEDED.value
        generation.candidate_json = json.dumps(
            _candidate_json(to_stored(candidate)), ensure_ascii=False, separators=(",", ":")
        )
        self._session.add(generation)
        self._session.flush()
        return _Generated(generation, candidate, truncated)

    def _save_failed(self, generation: AIGeneration, code: ErrorCode) -> None:
        """Ghi bản ghi FAILED bằng transaction riêng.

        Java không bọc generate() trong transaction nên bản ghi lỗi vẫn persist dù
        request trả 502/504. Ở đây request có transaction riêng sẽ rollback khi ném
        ApiException, nên phải ghi qua session độc lập.
        """
        from app.shared.database.session import SessionLocal

        generation.status = GenerationStatus.FAILED.value
        generation.error_code = code.value
        with SessionLocal() as independent:
            independent.add(generation)
            independent.commit()


def _check_source(request: GenerationRequest) -> int | None:
    if request.source_type is SourceType.DOCUMENT and request.document_id is None:
        raise ApiException.field_error(
            "document_id", "document_id is required when source_type is DOCUMENT"
        )
    if request.source_type is SourceType.TRANSCRIPT and request.document_id is not None:
        raise ApiException.field_error(
            "document_id", "document_id is only allowed when source_type is DOCUMENT"
        )
    return request.document_id


def _candidate_json(value) -> dict:  # noqa: ANN001
    if isinstance(value, QuizCandidate):
        return {"questions": _questions_json(value.questions)}
    if isinstance(value, FlashcardCandidate):
        return {"flashcards": _cards_json(value.flashcards)}
    raise TypeError(f"Unsupported candidate type: {type(value)!r}")


def _questions_json(questions: list[QuestionCandidate]) -> list[dict]:
    return [
        {
            "content": question.content,
            "options": [
                {"content": option.content, "is_correct": option.is_correct}
                for option in question.options
            ],
            "explanation": question.explanation,
        }
        for question in questions
    ]


def _cards_json(cards: list[CardCandidate]) -> list[dict]:
    return [
        {"front_text": card.front_text, "back_text": card.back_text} for card in cards
    ]
