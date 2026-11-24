
from __future__ import annotations

from dataclasses import dataclass, field

from app.shared.error.codes import ErrorCode, default_message


@dataclass(frozen=True)
class FieldError:
    field: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


@dataclass
class ApiException(Exception):
    code: ErrorCode
    message: str = ""
    details: list[FieldError] | None = field(default=None)

    def __post_init__(self) -> None:
        if not self.message:
            self.message = default_message(self.code)
        super().__init__(self.message)

    @classmethod
    def field_error(cls, field_name: str, message: str) -> ApiException:
        return cls(
            ErrorCode.VALIDATION_ERROR,
            default_message(ErrorCode.VALIDATION_ERROR),
            [FieldError(field_name, message)],
        )

    @classmethod
    def of(cls, code: ErrorCode, message: str | None = None) -> ApiException:
        return cls(code, message or default_message(code))


class StorageException(Exception):
    pass


class InvalidCandidateException(Exception):
    pass


class CandidateSourceError(Exception):
    pass
