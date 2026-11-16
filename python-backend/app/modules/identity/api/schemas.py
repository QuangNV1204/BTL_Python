"""Request/response của module identity.

Field name khớp DTO Java. Vì JSON dùng snake_case, model dùng đúng tên snake_case;
client muốn camelCase cũng được nhờ AliasChoices ở nơi cần (ví dụ full_name).
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.shared.domain.enums import TeacherRequestStatus, UserRole
from app.shared.http.serialization import Instant


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class RegisterRequest(_Request):
    full_name: Annotated[str, Field(max_length=120)] = Field(
        validation_alias=AliasChoices("full_name", "fullName")
    )
    email: Annotated[str, Field(max_length=254)]
    password: Annotated[str, Field(min_length=10, max_length=72)]

    @field_validator("full_name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Full name must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def _email_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Email must not be blank")
        if not _EMAIL.fullmatch(value.strip()):
            raise ValueError("Invalid email format")
        return value

    @field_validator("password")
    @classmethod
    def _password_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password must not be blank")
        return value


class LoginRequest(_Request):
    email: Annotated[str, Field(max_length=254)]
    password: Annotated[str, Field(max_length=72)]

    @field_validator("email")
    @classmethod
    def _email_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Email must not be blank")
        return value

    @field_validator("password")
    @classmethod
    def _password_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password must not be blank")
        return value


class ChangePasswordRequest(_Request):
    current_password: Annotated[str, Field(max_length=72)] = Field(
        validation_alias=AliasChoices("current_password", "currentPassword")
    )
    new_password: Annotated[str, Field(min_length=10, max_length=72)] = Field(
        validation_alias=AliasChoices("new_password", "newPassword")
    )

    @field_validator("current_password")
    @classmethod
    def _current_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Current password must not be blank")
        return value

    @field_validator("new_password")
    @classmethod
    def _new_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("New password must not be blank")
        return value


class _EmailOnlyRequest(_Request):
    email: Annotated[str, Field(max_length=254)]

    @field_validator("email")
    @classmethod
    def _blank_and_format(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Email must not be blank")
        if not _EMAIL.fullmatch(value.strip()):
            raise ValueError("Invalid email format")
        return value


class ForgotPasswordRequest(_EmailOnlyRequest):
    pass


class ResendVerificationEmailRequest(_EmailOnlyRequest):
    pass


class _TokenRequest(_Request):
    token: Annotated[str, Field(pattern=r"[A-Za-z0-9_-]{43}")]

    @field_validator("token")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Token must not be blank")
        return value


class VerifyEmailRequest(_TokenRequest):
    pass


class ResetPasswordRequest(_Request):
    token: Annotated[str, Field(pattern=r"[A-Za-z0-9_-]{43}")]
    new_password: Annotated[str, Field(min_length=10, max_length=72)] = Field(
        validation_alias=AliasChoices("new_password", "newPassword")
    )

    @field_validator("token")
    @classmethod
    def _token_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Reset token must not be blank")
        return value

    @field_validator("new_password")
    @classmethod
    def _new_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("New password must not be blank")
        return value


class UpdateProfileRequest(_Request):
    full_name: Annotated[str, Field(max_length=120)] = Field(
        validation_alias=AliasChoices("full_name", "fullName")
    )

    @field_validator("full_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Full name must not be blank")
        return value


class UpdateUserStatusRequest(_Request):
    is_active: bool = Field(validation_alias=AliasChoices("is_active", "isActive"))


class CreateTeacherRequest(_Request):
    reason: Annotated[str, Field(max_length=4000)]

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Reason must not be blank")
        return value


class TeacherDecisionRequest(_Request):
    status: TeacherRequestStatus
    decision_note: Annotated[str | None, Field(max_length=4000)] = Field(
        default=None, validation_alias=AliasChoices("decision_note", "decisionNote")
    )


# ---- response ----


class UserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    created_at: Instant


class AuthResponse(BaseModel):
    access_token: str


class TeacherRequestResponse(BaseModel):
    id: str
    user_id: str
    reason: str
    status: TeacherRequestStatus
    decided_by: str | None = None
    decision_note: str | None = None
    decided_at: Instant | None = None
    created_at: Instant


_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def user_response(user) -> UserResponse:  # noqa: ANN001
    return UserResponse(
        id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        role=UserRole(user.role),
        is_active=bool(user.is_active),
        created_at=user.created_at,
    )


def teacher_request_response(row) -> TeacherRequestResponse:  # noqa: ANN001
    return TeacherRequestResponse(
        id=str(row.id),
        user_id=str(row.user_id),
        reason=row.reason,
        status=TeacherRequestStatus(row.status),
        decided_by=None if row.decided_by is None else str(row.decided_by),
        decision_note=row.decision_note,
        decided_at=row.decided_at,
        created_at=row.created_at,
    )
