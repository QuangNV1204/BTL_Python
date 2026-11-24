
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.auth.refresh_tokens import generate_token, hash_token
from app.shared.database.base import utcnow
from app.shared.database.models import EmailVerificationToken, User
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.mail.email_service import EmailService

TOKEN_TTL = timedelta(hours=24)


class EmailVerificationService:
    def __init__(self, session: Session, email_service: EmailService) -> None:
        self._session = session
        self._email_service = email_service

    def send_verification_email(self, user: User) -> None:
        token = generate_token()
        now = utcnow()
        self._session.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=now + TOKEN_TTL,
            )
        )
        self._session.flush()
        self._email_service.send_verification_email(user.email, token)

    def verify_email(self, token: str) -> None:
        row = self._session.scalars(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.token_hash == hash_token(token))
            .with_for_update()
        ).first()
        if row is None:
            raise ApiException(ErrorCode.INVALID_EMAIL_VERIFICATION_TOKEN)

        now = utcnow()
        if row.used_at is not None or not row.expires_at > now:
            raise ApiException(ErrorCode.INVALID_EMAIL_VERIFICATION_TOKEN)

        user = row.user
        if user is None or not user.is_active:
            raise ApiException(ErrorCode.ACCOUNT_INACTIVE)

        row.used_at = now
        if user.email_verified_at is None:
            user.email_verified_at = now
            user.updated_at = now

    def resend_verification_email(self, email: str) -> None:
        user = self._session.scalars(
            select(User).where(User.email == email.strip().lower())
        ).first()

        if user is None or user.email_verified_at is not None or not user.is_active:
            return
        self.send_verification_email(user)
