
from __future__ import annotations

import logging
from dataclasses import dataclass

import bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.identity.api.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserResponse,
    user_response,
)
from app.modules.identity.application.email_verification_service import (
    EmailVerificationService,
)
from app.modules.identity.application.teacher_request_service import (
    TeacherRequestService,
)
from app.shared.auth.jwt_service import JwtService
from app.shared.auth.principal import AuthenticatedUser
from app.shared.auth.refresh_tokens import RefreshTokenService
from app.shared.database.base import utcnow
from app.shared.database.models import User
from app.shared.domain.enums import UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException

logger = logging.getLogger("learningai.auth")


@dataclass
class AuthTokenResult:
    access_token: str
    refresh_token: str


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


class AuthService:
    def __init__(
        self,
        session: Session,
        jwt_service: JwtService,
        refresh_tokens: RefreshTokenService,
        email_verification: EmailVerificationService,
        teacher_requests: TeacherRequestService,
    ) -> None:
        self._session = session
        self._jwt = jwt_service
        self._refresh = refresh_tokens
        self._email_verification = email_verification
        self._teacher_requests = teacher_requests

    def login(self, request: LoginRequest) -> AuthTokenResult:
        email = request.email.strip().lower()
        user = self._session.scalars(select(User).where(User.email == email)).first()
        if user is None or not verify_password(request.password, user.password_hash):
            raise ApiException(ErrorCode.UNAUTHENTICATED)
        if not user.is_active:
            raise ApiException(ErrorCode.ACCOUNT_INACTIVE)
        if user.email_verified_at is None:
            raise ApiException(ErrorCode.EMAIL_NOT_VERIFIED)

        access_token = self._jwt.generate_token(user)
        refresh = self._refresh.create_refresh_token(user.id)
        return AuthTokenResult(access_token, refresh.refresh_token)

    def register(self, request: RegisterRequest) -> UserResponse:
        now = utcnow()
        user = User(
            full_name=request.full_name,
            email=request.email.strip().lower(),
            password_hash=hash_password(request.password),
            role=UserRole.STUDENT.value,
            is_active=True,
            email_verified_at=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(user)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ApiException(ErrorCode.EMAIL_ALREADY_EXISTS) from exc


        self._email_verification.send_verification_email(user)
        return user_response(user)

    def refresh_token(self, refresh_token: str | None) -> AuthTokenResult:
        if refresh_token is None or not refresh_token.strip():
            raise ApiException(ErrorCode.UNAUTHENTICATED)

        rotated = self._refresh.rotate_refresh_token(refresh_token)
        user = self._session.get(User, rotated.user_id)
        if user is None:
            raise ApiException(ErrorCode.UNAUTHENTICATED)
        if not user.is_active:
            raise ApiException(ErrorCode.ACCOUNT_INACTIVE)
        if user.email_verified_at is None:
            raise ApiException(ErrorCode.EMAIL_NOT_VERIFIED)

        return AuthTokenResult(self._jwt.generate_token(user), rotated.refresh_token)

    def change_password(self, principal: AuthenticatedUser, request: ChangePasswordRequest) -> None:
        user = self._session.get(User, principal.user_id)
        if user is None:
            raise ApiException(ErrorCode.UNAUTHENTICATED)
        if not user.is_active:
            raise ApiException(ErrorCode.ACCOUNT_INACTIVE)
        if not verify_password(request.current_password, user.password_hash):
            raise ApiException.field_error("current_password", "Current password is incorrect")
        if request.new_password == request.current_password:
            raise ApiException.field_error(
                "new_password", "New password must differ from current password"
            )
        user.password_hash = hash_password(request.new_password)
        user.updated_at = utcnow()

    def logout(self, refresh_token: str | None) -> None:
        self._refresh.revoke_refresh_token(refresh_token)

    def logout_all(self, principal: AuthenticatedUser) -> None:
        self._refresh.revoke_all_for_user(principal.user_id)
