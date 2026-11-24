
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import PurePath

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.lesson.api.schemas import (
    LessonDocumentResponse,
    LessonReorderRequest,
    LessonResponse,
    LessonWriteRequest,
)
from app.modules.lesson.application.access_policy import (
    LessonAccessPolicy,
    LessonViewAccess,
)
from app.modules.lesson.application.cleanup_service import DocumentCleanupService
from app.shared.config.settings import Settings
from app.shared.database.base import utcnow
from app.shared.database.models import (
    Flashcard,
    Lesson,
    LessonDocument,
    Quiz,
    QuizAttempt,
)
from app.shared.domain.enums import SourceType
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.storage.documents import (
    ALLOWED_MEDIA_TYPES,
    DocumentStorage,
    extract_text,
)

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class UploadedDocument:

    filename: str | None
    content_type: str | None
    content: bytes

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class DocumentDownload:
    content: bytes
    original_name: str
    media_type: str


class LessonService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        storage: DocumentStorage,
        policy: LessonAccessPolicy,
    ) -> None:
        self._session = session
        self._settings = settings
        self._storage = storage
        self._policy = policy
        self._cleanup = DocumentCleanupService(session, storage)


    def list_for_course(self, course_id: int, user_id: int) -> list[LessonResponse]:
        include_transcript = (
            self._policy.assert_can_view_course(course_id, user_id) is LessonViewAccess.MANAGER
        )
        lessons = self._session.scalars(
            select(Lesson)
            .where(Lesson.course_id == course_id)
            .order_by(Lesson.order_index.asc())
        ).all()
        return [self._to_response(lesson, include_transcript) for lesson in lessons]

    def get(self, lesson_id: int, user_id: int) -> LessonResponse:
        lesson = self._policy.lesson_context(lesson_id)
        access = self._policy.assert_can_view_lesson(lesson_id, user_id)
        return self._to_response(lesson, access is LessonViewAccess.MANAGER)


    def create(self, course_id: int, request: LessonWriteRequest, user_id: int) -> LessonResponse:
        self._policy.assert_can_manage_course(course_id, user_id)
        lessons = self._lock_course_lessons(course_id)
        now = utcnow()
        lesson = Lesson(
            course_id=course_id,
            title=request.title.strip(),
            video_url=(request.video_url or "").strip(),
            transcript_text=_normalize_optional(request.transcript_text),
            order_index=len(lessons) + 1,
            created_at=now,
            updated_at=now,
        )
        self._session.add(lesson)
        self._session.flush()
        return self._to_response(lesson, include_transcript=True)

    def update(self, lesson_id: int, request: LessonWriteRequest, user_id: int) -> LessonResponse:
        lesson = self._policy.assert_can_manage_lesson(lesson_id, user_id)

        lesson.title = request.title.strip()
        lesson.video_url = (request.video_url or "").strip()
        lesson.transcript_text = _normalize_optional(request.transcript_text)
        lesson.updated_at = utcnow()
        self._session.flush()
        return self._to_response(lesson, include_transcript=True)

    def reorder(
        self, course_id: int, request: LessonReorderRequest, user_id: int
    ) -> list[LessonResponse]:
        self._policy.assert_can_manage_course(course_id, user_id)
        lessons = self._lock_course_lessons(course_id)
        requested = request.lesson_ids
        existing = {lesson.id for lesson in lessons}
        if (
            len(requested) != len(lessons)
            or len(set(requested)) != len(requested)
            or set(requested) != existing
        ):
            raise ApiException(
                ErrorCode.VALIDATION_ERROR,
                "lesson_ids must contain every lesson of the course exactly once",
            )

        size = len(lessons)

        for index, lesson in enumerate(lessons):
            lesson.order_index = index + size + 1000
        self._session.flush()

        by_id = {lesson.id: lesson for lesson in lessons}
        for index, lesson_id in enumerate(requested):
            by_id[lesson_id].order_index = index + 1
        self._session.flush()
        return [self._to_response(by_id[lesson_id], True) for lesson_id in requested]

    def delete(self, lesson_id: int, user_id: int) -> None:
        lesson = self._policy.assert_can_manage_lesson(lesson_id, user_id)
        if self._count_quiz_attempts(lesson_id) > 0:
            raise ApiException(ErrorCode.LESSON_DELETE_BLOCKED)
        if self._count_quizzes(lesson_id) > 0 or self._count_flashcards(lesson_id) > 0:
            raise ApiException(
                ErrorCode.INVALID_STATE,
                "Delete draft quiz and flashcard content before deleting the lesson",
            )

        documents = self._documents_of(lesson_id)
        for document in documents:
            self._cleanup.after_commit(document.storage_key)
            self._session.delete(document)
        self._session.delete(lesson)
        self._session.flush()
        self._compact_orders(lesson.course_id)


    def list_documents(self, lesson_id: int, user_id: int) -> list[LessonDocumentResponse]:
        self._policy.assert_can_view_lesson(lesson_id, user_id)
        return [self._to_document_response(row) for row in self._documents_of(lesson_id)]

    def upload_document(
        self, lesson_id: int, file: UploadedDocument, user_id: int
    ) -> LessonDocumentResponse:
        self._policy.assert_can_manage_lesson(lesson_id, user_id)
        _validate_document(file)

        extracted = extract_text(file.content, file.content_type or "")
        storage_key = self._storage.new_key(file.filename)
        self._cleanup.stage_upload(storage_key)
        self._storage.store(storage_key, file.content)

        now = utcnow()
        document = LessonDocument(
            lesson_id=lesson_id,
            uploaded_by=user_id,
            original_name=_safe_original_name(file.filename),
            storage_key=storage_key,
            media_type=file.content_type or "",
            size_bytes=file.size,
            extracted_text=extracted,
            content_hash=hashlib.sha256(file.content).hexdigest(),
            created_at=now,
        )
        self._session.add(document)
        self._session.flush()
        self._cleanup.adopt_upload(storage_key)
        return self._to_document_response(document)

    def download_document(self, document_id: int, user_id: int) -> DocumentDownload:
        document = self._document(document_id)
        self._policy.assert_can_view_lesson(document.lesson_id, user_id)
        return DocumentDownload(
            content=self._storage.load(document.storage_key),
            original_name=document.original_name,
            media_type=document.media_type,
        )

    def delete_document(self, document_id: int, user_id: int) -> None:
        document = self._document(document_id)
        self._policy.assert_can_manage_lesson(document.lesson_id, user_id)
        self._cleanup.after_commit(document.storage_key)
        self._session.delete(document)
        self._session.flush()


    def get_source_text(
        self, lesson_id: int, source_type: SourceType, document_id: int | None
    ) -> str:
        lesson = self._policy.lesson_context(lesson_id)
        if source_type is SourceType.TRANSCRIPT:
            text = lesson.transcript_text
        elif source_type is SourceType.DOCUMENT:
            if document_id is None:
                raise ApiException(
                    ErrorCode.VALIDATION_ERROR, "document_id is required for DOCUMENT source"
                )
            document = self._session.scalars(
                select(LessonDocument).where(
                    LessonDocument.id == document_id,
                    LessonDocument.lesson_id == lesson_id,
                )
            ).first()
            if document is None:
                raise ApiException(
                    ErrorCode.NOT_FOUND, "Document does not belong to lesson"
                )
            text = document.extracted_text
        else:
            raise ApiException(ErrorCode.VALIDATION_ERROR, "Unsupported source type")

        if text is None or not text.strip():
            raise ApiException(ErrorCode.SOURCE_TEXT_EMPTY)
        return text


    def _lock_course_lessons(self, course_id: int) -> list[Lesson]:
        return list(
            self._session.scalars(
                select(Lesson)
                .where(Lesson.course_id == course_id)
                .order_by(Lesson.order_index.asc())
                .with_for_update()
            ).all()
        )

    def _compact_orders(self, course_id: int) -> None:
        lessons = self._lock_course_lessons(course_id)
        for index, lesson in enumerate(lessons):
            lesson.order_index = index + 1
        self._session.flush()

    def _documents_of(self, lesson_id: int) -> list[LessonDocument]:
        return list(
            self._session.scalars(
                select(LessonDocument)
                .where(LessonDocument.lesson_id == lesson_id)
                .order_by(LessonDocument.created_at.asc())
            ).all()
        )

    def _document(self, document_id: int) -> LessonDocument:
        document = self._session.get(LessonDocument, document_id)
        if document is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Document not found")
        return document

    def _count_quiz_attempts(self, lesson_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(QuizAttempt)
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(Quiz.lesson_id == lesson_id)
            )
            or 0
        )

    def _count_quizzes(self, lesson_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(Quiz).where(Quiz.lesson_id == lesson_id)
            )
            or 0
        )

    def _count_flashcards(self, lesson_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(Flashcard)
                .where(Flashcard.lesson_id == lesson_id)
            )
            or 0
        )

    def _count_documents(self, lesson_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(LessonDocument)
                .where(LessonDocument.lesson_id == lesson_id)
            )
            or 0
        )

    def _to_response(self, lesson: Lesson, include_transcript: bool) -> LessonResponse:
        blocked = self._count_quiz_attempts(lesson.id) > 0
        return LessonResponse(
            id=lesson.id,
            course_id=lesson.course_id,
            title=lesson.title,
            video_url=lesson.video_url,
            transcript_text=lesson.transcript_text if include_transcript else None,
            order_index=lesson.order_index,
            document_count=self._count_documents(lesson.id),
            quiz_count=self._count_quizzes(lesson.id),
            flashcard_count=self._count_flashcards(lesson.id),
            can_delete=not blocked,
            delete_blocked_reason="Bài học đã có lịch sử làm quiz." if blocked else None,
            created_at=lesson.created_at,
            updated_at=lesson.updated_at,
        )

    @staticmethod
    def _to_document_response(document: LessonDocument) -> LessonDocumentResponse:
        return LessonDocumentResponse(
            id=document.id,
            lesson_id=document.lesson_id,
            original_name=document.original_name,
            media_type=document.media_type,
            size_bytes=document.size_bytes,
            text_extracted=document.extracted_text is not None,
            created_at=document.created_at,
        )


def _validate_document(file: UploadedDocument) -> None:
    if not file.content:
        raise ApiException(ErrorCode.VALIDATION_ERROR, "Document is empty")
    if file.size > MAX_DOCUMENT_BYTES:
        raise ApiException(ErrorCode.FILE_TOO_LARGE)
    if file.content_type not in ALLOWED_MEDIA_TYPES:
        raise ApiException(ErrorCode.UNSUPPORTED_FILE_TYPE)


def _safe_original_name(filename: str | None) -> str:
    name = PurePath((filename or "document").replace("\\", "/")).name
    return name if len(name) <= 255 else name[-255:]


def _normalize_optional(text: str | None) -> str | None:
    if text is None or not text.strip():
        return None
    return text.strip()
