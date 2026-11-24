
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.identity.api.schemas import ResetPasswordRequest
from app.modules.identity.application.auth_service import hash_password, verify_password
from app.shared.auth.refresh_tokens import (
    RefreshTokenService,
    generate_token,
    hash_token,
)
from app.shared.database.base import utcnow
from app.shared.database.models import PasswordResetToken, User
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.mail.email_service import EmailService

TOKEN_TTL = timedelta(minutes=30)


class PasswordResetService:
    def __init__(
        self,
        session: Session,
        email_service: EmailService,
        refresh_tokens: RefreshTokenService,
    ) -> None:
        self._session = session
        self._email_service = email_service
        self._refresh_tokens = refresh_tokens

    def forgot_password(self, email: str) -> None:
        user = self._session.scalars(
            select(User)
            .where(User.email == email.strip().lower())
            .with_for_update()
        ).first()

        if user is None or not user.is_active or user.email_verified_at is None:
            return

        now = utcnow()
        self._invalidate_all_for_user(user.id, now)
        token = generate_token()
        self._session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=now + TOKEN_TTL,
            )
        )
        self._session.flush()
        self._email_service.send_password_reset_email(user.email, token)

    def reset_password(self, request: ResetPasswordRequest) -> None:
        token_hash = hash_token(request.token)
        user = self._session.scalars(
            select(User)
            .join(PasswordResetToken, PasswordResetToken.user_id == User.id)
            .where(PasswordResetToken.token_hash == token_hash)
            .with_for_update()
        ).first()
        if user is None:
            raise ApiException(ErrorCode.INVALID_PASSWORD_RESET_TOKEN)

        row = self._session.scalars(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token_hash)
            .with_for_update()
        ).first()
        if row is None:
            raise ApiException(ErrorCode.INVALID_PASSWORD_RESET_TOKEN)

        now = utcnow()
        if row.used_at is not None or not row.expires_at > now:
            raise ApiException(ErrorCode.INVALID_PASSWORD_RESET_TOKEN)
        if not user.is_active:
            raise ApiException(ErrorCode.ACCOUNT_INACTIVE)
        if user.email_verified_at is None:
            raise ApiException(ErrorCode.EMAIL_NOT_VERIFIED)
        if verify_password(request.new_password, user.password_hash):
            raise ApiException.field_error(
                "new_password", "New password must differ from current password"
            )

        user.password_hash = hash_password(request.new_password)
        user.updated_at = now
        row.used_at = now
        self._invalidate_all_for_user(user.id, now)
        self._refresh_tokens.revoke_all_for_user(user.id)

    def _invalidate_all_for_user(self, user_id: int, now) -> None:
        self._session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )
