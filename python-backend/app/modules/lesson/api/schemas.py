"""Schema của module lesson; request theo LessonWriteRequest.java."""

from __future__ import annotations

from typing import Annotated

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.shared.http.serialization import Instant
from app.shared.validation.validators import is_youtube_url


class LessonWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=200)]
    video_url: str | None = Field(
        default=None,
        max_length=2048,
        validation_alias=AliasChoices("video_url", "videoUrl"),
    )
    transcript_text: str | None = Field(
        default=None, validation_alias=AliasChoices("transcript_text", "transcriptText")
    )

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("video_url")
    @classmethod
    def _youtube(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value
        if not is_youtube_url(value):
            raise ValueError("must be a valid YouTube URL")
        return value


class LessonReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_ids: list[int] = Field(validation_alias=AliasChoices("lesson_ids", "lessonIds"))

    @field_validator("lesson_ids")
    @classmethod
    def _not_empty(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("must not be empty")
        if any(item is None for item in value):
            raise ValueError("must not contain null")
        return value


class LessonDocumentResponse(BaseModel):
    id: int
    lesson_id: int
    original_name: str
    media_type: str
    size_bytes: int
    text_extracted: bool
    created_at: Instant


class LessonResponse(BaseModel):
    # LessonResponse.java dùng Long trần (không @JsonSerialize string) nên id là number.
    id: int
    course_id: int
    title: str
    video_url: str
    transcript_text: str | None
    order_index: int
    document_count: int
    quiz_count: int
    flashcard_count: int
    can_delete: bool
    delete_blocked_reason: str | None
    created_at: Instant
    updated_at: Instant
