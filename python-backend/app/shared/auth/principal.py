
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.shared.database.models import User
from app.shared.domain.enums import UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: int
    role: UserRole
    email: str
    is_active: bool
    email_verified: bool

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.ADMIN

    @property
    def is_teacher_or_admin(self) -> bool:
        return self.role in (UserRole.TEACHER, UserRole.ADMIN)

    @classmethod
    def build(cls, user: User) -> AuthenticatedUser:
        return cls(
            user_id=user.id,
            role=UserRole(user.role),
            email=user.email,
            is_active=bool(user.is_active),
            email_verified=user.email_verified_at is not None,
        )


def principal_of(request: Request) -> AuthenticatedUser:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise ApiException(ErrorCode.UNAUTHENTICATED)
    return principal


def optional_principal(request: Request) -> AuthenticatedUser | None:
    return getattr(request.state, "principal", None)
