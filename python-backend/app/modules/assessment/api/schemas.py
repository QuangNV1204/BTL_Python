"""Schema quiz — giữ đúng validate nghiêm ngặt của DTO Java.

Các body quiz được Java parse thủ công để từ chối field lạ/dấu sai kiểu với thông
điệp riêng. Ở đây dùng ``model_validator(mode="before")`` trên dict thô để giữ
cùng thông điệp và cùng quy tắc.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.shared.domain.enums import QuizStatus
from app.shared.error.exceptions import ApiException
from app.shared.http.serialization import Instant

_BIGINT = re.compile(r"[1-9][0-9]{0,18}")
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_WHITESPACE = re.compile(r"\s+")
_MAX_BIGINT = 2**63 - 1


def _invalid(message: str) -> ApiException:
    from app.shared.error.codes import ErrorCode

    return ApiException(ErrorCode.VALIDATION_ERROR, message)


def _fields(body: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise _invalid("Expected an object")
    for name in body:
        if name not in allowed:
            raise _invalid(f"Unknown field: {name}")
    return body


def _code_points(value: str) -> int:
    return len(value)


def _text(value: Any, field_name: str, max_len: int, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _code_points(value) > max_len:
        raise _invalid(f"Invalid {field_name}")
    if not nullable and not _WHITESPACE.sub("", value):
        raise _invalid(f"Invalid {field_name}")
    return value


def _valid_text(value: str | None, max_len: int) -> bool:
    return value is not None and bool(_WHITESPACE.sub("", value)) and _code_points(value) <= max_len


def _position(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _invalid("order_index must be a non-negative integer")
    if value > 2**31 - 1:
        raise _invalid("order_index must be a non-negative integer")
    return value


def _positive_bigint_str(value: Any, field_name: str) -> int:
    if not isinstance(value, str) or not _BIGINT.fullmatch(value):
        raise _invalid(f"{field_name} must be a positive BIGINT string")
    number = int(value)
    if number > _MAX_BIGINT:
        raise _invalid(f"{field_name} exceeds the signed BIGINT range")
    return number


def normalize_option_text(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", value)).strip().lower()


# ---------------------------------------------------------------------- options
class OptionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    is_correct: bool
    order_index: int


def _parse_option(value: Any) -> OptionWrite:
    body = _fields(value, {"content", "is_correct", "order_index"})
    correct = body.get("is_correct")
    if not isinstance(correct, bool):
        raise _invalid("is_correct must be a boolean")
    return OptionWrite(
        content=_text(body.get("content"), "options.content", 1000, nullable=False) or "",
        is_correct=correct,
        order_index=_position(body.get("order_index")),
    )


# --------------------------------------------------------------------- question
class WriteQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    explanation: str | None
    order_index: int
    options: list[OptionWrite]
    generation_id: int | None = None

    @field_validator("options")
    @classmethod
    def _validate_options(cls, value: list[OptionWrite]) -> list[OptionWrite]:
        return value

    def validate_rules(self) -> None:
        """Sao WriteQuestionRequest.validate(): nội dung và đúng một đáp án đúng."""
        if (
            not _valid_text(self.content, 4000)
            or (self.explanation is not None and _code_points(self.explanation) > 4000)
            or self.order_index is None
            or self.order_index < 0
            or len(self.options) < 2
            or len(self.options) > 6
        ):
            raise _invalid("Invalid question content or options")

        contents: set[str] = set()
        positions: set[int] = set()
        correct_count = 0
        for option in self.options:
            if (
                not _valid_text(option.content, 1000)
                or option.is_correct is None
                or option.order_index is None
                or option.order_index < 0
            ):
                raise _invalid("Invalid option")
            normalized = normalize_option_text(option.content)
            if normalized in contents:
                raise _invalid("Option content must be unique after normalization")
            contents.add(normalized)
            if option.order_index in positions:
                from app.shared.error.codes import ErrorCode

                raise ApiException(
                    ErrorCode.INVALID_STATE, "Option order_index must be unique"
                )
            positions.add(option.order_index)
            if option.is_correct:
                correct_count += 1
        if correct_count != 1:
            raise _invalid("Exactly one option must be correct")

    @classmethod
    def from_json(cls, body: Any) -> WriteQuestionRequest:
        fields = _fields(
            body, {"content", "explanation", "order_index", "options", "generation_id"}
        )
        content = _text(fields.get("content"), "content", 4000, nullable=False) or ""
        if "explanation" not in fields:
            raise _invalid("explanation is required")
        explanation = _text(fields.get("explanation"), "explanation", 4000, nullable=True)
        order_index = _position(fields.get("order_index"))

        options_raw = fields.get("options")
        if not isinstance(options_raw, list) or not 2 <= len(options_raw) <= 6:
            raise _invalid("options must contain 2 to 6 items")
        options = [_parse_option(item) for item in options_raw]

        generation = fields.get("generation_id")
        generation_id = None
        if generation is not None:
            generation_id = _positive_bigint_str(generation, "generation_id")

        request = cls(
            content=content,
            explanation=explanation,
            order_index=order_index,
            options=options,
            generation_id=generation_id,
        )
        request.validate_rules()
        return request


# ------------------------------------------------------------------------- quiz
class CreateQuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    generation_id: int | None = None

    @classmethod
    def from_json(cls, body: Any) -> CreateQuizRequest:
        if not isinstance(body, dict):
            raise _invalid("Request body must be an object")
        fields = _fields(body, {"title", "generation_id"})
        title = fields.get("title")
        if (
            not isinstance(title, str)
            or not title.strip()
            or _code_points(title) > 200
        ):
            raise _invalid("title must be a non-blank string of at most 200 characters")
        generation = fields.get("generation_id")
        generation_id = (
            None
            if generation is None
            else _positive_bigint_str(generation, "generation_id")
        )
        return cls(title=title, generation_id=generation_id)


class UpdateQuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    generation_id: int | None = None

    @classmethod
    def from_json(cls, body: Any) -> UpdateQuizRequest:
        if not isinstance(body, dict) or not body:
            raise _invalid("Request body must be an object")
        fields = _fields(body, {"title", "generation_id"})
        title = fields.get("title")
        if title is not None and (
            not isinstance(title, str) or not title.strip() or _code_points(title) > 200
        ):
            raise _invalid("title must be a non-blank string of at most 200 characters")
        generation = fields.get("generation_id")
        generation_id = (
            None
            if generation is None
            else _positive_bigint_str(generation, "generation_id")
        )
        return cls(title=title, generation_id=generation_id)


class QuizPublicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: QuizStatus

    @classmethod
    def from_json(cls, body: Any) -> QuizPublicationRequest:
        if not isinstance(body, dict) or len(body) != 1 or "status" not in body:
            raise _invalid("Only status is allowed and required")
        status = body["status"]
        if status not in ("PUBLISHED", "CLOSED"):
            raise _invalid("status must be PUBLISHED or CLOSED")
        return cls(status=QuizStatus(status))


class SaveDraftItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None
    question: WriteQuestionRequest


class SaveQuizDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    title: str
    questions: list[SaveDraftItem]

    @classmethod
    def from_json(cls, body: Any) -> SaveQuizDraftRequest:
        _fields(body, {"request_id", "title", "questions"})

        key = body.get("request_id")
        if not isinstance(key, str) or not _UUID.fullmatch(key):
            raise _invalid("request_id must be a UUID")

        title = body.get("title")
        if not isinstance(title, str) or not title.strip() or _code_points(title) > 200:
            raise _invalid("title must contain 1 to 200 characters")

        values = body.get("questions")
        if not isinstance(values, list) or len(values) > 200:
            raise _invalid("questions must be an array of at most 200 items")

        items: list[SaveDraftItem] = []
        ids: set[int] = set()
        positions: set[int] = set()
        for value in values:
            _fields(
                value,
                {"id", "content", "explanation", "order_index", "options", "generation_id"},
            )
            question_id: int | None = None
            raw_id = value.get("id")
            if "id" in value and raw_id is not None:
                if not isinstance(raw_id, str) or not _BIGINT.fullmatch(raw_id):
                    raise _invalid("Invalid question id")
                question_id = int(raw_id)
                if question_id > _MAX_BIGINT:
                    raise _invalid("Question id exceeds signed BIGINT")
                if question_id in ids:
                    raise _invalid("Duplicate question id")
                ids.add(question_id)

            question_body = {k: v for k, v in value.items() if k != "id"}
            write = WriteQuestionRequest.from_json(question_body)
            if write.order_index in positions:
                raise _invalid("Duplicate question order_index")
            positions.add(write.order_index)
            items.append(SaveDraftItem(id=question_id, question=write))

        # Thứ tự mảng là thứ tự hiển thị cuối cùng; không cho vị trí mơ hồ.
        for index, item in enumerate(items):
            if item.question.order_index != index:
                raise _invalid("Question order_index must match array position")

        return cls(request_id=key.lower(), title=title, questions=items)


# -------------------------------------------------------------------- response
class OptionAuthor(BaseModel):
    id: str
    content: str
    is_correct: bool
    order_index: int


class QuestionAuthor(BaseModel):
    id: str
    content: str
    explanation: str | None
    order_index: int
    generated_by_ai: bool
    options: list[OptionAuthor]


class QuizAuthorResponse(BaseModel):
    id: str
    lesson_id: str
    title: str
    status: QuizStatus
    created_at: Instant
    questions: list[QuestionAuthor]


class StudentOption(BaseModel):
    id: str
    content: str
    order_index: int


class StudentQuestion(BaseModel):
    id: str
    content: str
    order_index: int
    options: list[StudentOption]


class QuizStudentResponse(BaseModel):
    id: str
    lesson_id: str
    title: str
    status: QuizStatus
    questions: list[StudentQuestion]


class QuizSummaryResponse(BaseModel):
    id: str
    lesson_id: str
    title: str
    status: QuizStatus
    question_count: int


def quiz_author_response(quiz, questions, options_by_question) -> QuizAuthorResponse:  # noqa: ANN001
    ordered = sorted(questions, key=lambda item: item.order_index)
    return QuizAuthorResponse(
        id=str(quiz.id),
        lesson_id=str(quiz.lesson_id),
        title=quiz.title,
        status=QuizStatus(quiz.status),
        created_at=quiz.created_at,
        questions=[
            QuestionAuthor(
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
                    for option in sorted(
                        options_by_question.get(question.id, []),
                        key=lambda item: item.order_index,
                    )
                ],
            )
            for question in ordered
        ],
    )


def quiz_student_response(quiz, questions, options_by_question) -> QuizStudentResponse:  # noqa: ANN001
    ordered = sorted(questions, key=lambda item: item.order_index)
    return QuizStudentResponse(
        id=str(quiz.id),
        lesson_id=str(quiz.lesson_id),
        title=quiz.title,
        status=QuizStatus(quiz.status),
        questions=[
            StudentQuestion(
                id=str(question.id),
                content=question.content,
                order_index=question.order_index,
                options=[
                    StudentOption(
                        id=str(option.id),
                        content=option.content,
                        order_index=option.order_index,
                    )
                    for option in sorted(
                        options_by_question.get(question.id, []),
                        key=lambda item: item.order_index,
                    )
                ],
            )
            for question in ordered
        ],
    )
