
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.shared.domain.enums import AttemptStatus
from app.shared.error.exceptions import ApiException
from app.shared.http.serialization import Instant, ScoreNumber


class AnswerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    selected_option_id: str | None


class SubmitAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[AnswerBody]

    @classmethod
    def from_json(cls, body: Any) -> SubmitAttemptRequest:
        from app.shared.error.codes import ErrorCode

        def invalid(message: str) -> ApiException:
            return ApiException(ErrorCode.VALIDATION_ERROR, message)

        if not isinstance(body, dict) or len(body) != 1 or "answers" not in body:
            raise invalid("Only answers is allowed and required")
        if any(name != "answers" for name in body):
            unknown = next(name for name in body if name != "answers")
            raise invalid(f"Unknown field: {unknown}")
        values = body["answers"]
        if not isinstance(values, list):
            raise invalid("answers must be an array")

        answers: list[AnswerBody] = []
        for value in values:
            if (
                not isinstance(value, dict)
                or "question_id" not in value
                or "selected_option_id" not in value
            ):
                raise invalid("Each answer requires question_id and selected_option_id")
            for name in value:
                if name not in ("question_id", "selected_option_id"):
                    raise invalid(f"Unknown answer field: {name}")
            question_id = _positive_id(value["question_id"], "question_id")
            option = value["selected_option_id"]
            selected = None if option is None else _positive_id(option, "selected_option_id")
            answers.append(AnswerBody(question_id=question_id, selected_option_id=selected))
        return cls(answers=answers)


def _positive_id(value: Any, field_name: str) -> str:
    import re

    from app.shared.error.codes import ErrorCode

    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", value):
        raise ApiException(
            ErrorCode.VALIDATION_ERROR, f"{field_name} must be a positive BIGINT string"
        )
    if int(value) > 2**63 - 1:
        raise ApiException(
            ErrorCode.VALIDATION_ERROR, f"{field_name} exceeds the signed BIGINT range"
        )
    return value


class AttemptResponse(BaseModel):
    id: str
    quiz_id: str
    student_id: str
    status: AttemptStatus
    total_questions: int
    started_at: Instant


class AttemptSummaryResponse(BaseModel):
    id: str
    quiz_id: str
    quiz_title: str
    course_id: str
    course_title: str
    status: AttemptStatus
    score: ScoreNumber | None
    started_at: Instant
    submitted_at: Instant | None


class ReviewOption(BaseModel):
    id: str
    content: str


class ReviewItem(BaseModel):
    question_id: str
    question_content: str
    selected_option_id: str | None
    is_correct: bool
    correct_option_id: str
    explanation: str | None
    options: list[ReviewOption]


class AttemptResultResponse(BaseModel):
    id: str
    quiz_id: str
    quiz_title: str
    student_id: str
    status: AttemptStatus
    score: ScoreNumber | None
    total_questions: int
    correct_count: int | None
    started_at: Instant
    submitted_at: Instant | None
    review: list[ReviewItem]


_ = Decimal
