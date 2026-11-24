
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.shared.domain.enums import FlashcardStatus
from app.shared.http.serialization import Instant


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CardWriteRequest(_Request):
    front_text: str = Field(max_length=4000, validation_alias=AliasChoices("front_text", "frontText"))
    back_text: str = Field(max_length=4000, validation_alias=AliasChoices("back_text", "backText"))
    generation_id: int | None = Field(
        default=None, validation_alias=AliasChoices("generation_id", "generationId")
    )

    @field_validator("front_text", "back_text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class CardUpdateRequest(_Request):
    front_text: str | None = Field(
        default=None, max_length=4000, validation_alias=AliasChoices("front_text", "frontText")
    )
    back_text: str | None = Field(
        default=None, max_length=4000, validation_alias=AliasChoices("back_text", "backText")
    )

    @field_validator("front_text", "back_text")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:

        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class StatusRequest(_Request):
    status: FlashcardStatus


class CardResponse(BaseModel):
    id: str
    lesson_id: str
    front_text: str
    back_text: str
    status: FlashcardStatus
    generated_by_ai: bool
    created_at: Instant


def card_response(card) -> CardResponse:
    return CardResponse(
        id=str(card.id),
        lesson_id=str(card.lesson_id),
        front_text=card.front_text,
        back_text=card.back_text,
        status=FlashcardStatus(card.status),
        generated_by_ai=bool(card.generated_by_ai),
        created_at=card.created_at,
    )
