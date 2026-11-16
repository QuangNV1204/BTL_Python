"""Refresh session và cookie, tương ứng RefreshTokenService/CookieService của Java.

Token ngẫu nhiên 32 byte Base64URL không padding (43 ký tự) — trùng định dạng mà
DTO verify/reset yêu cầu ``[A-Za-z0-9_-]{43}``. DB chỉ lưu SHA-256 hex của token.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.shared.config.settings import Settings
from app.shared.database.base import utcnow
from app.shared.database.models import AuthSession, User
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException

COOKIE_NAME = "refreshToken"
COOKIE_PATH = "/api/v1/auth"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", errors="strict")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class RefreshTokenResult:
    refresh_token: str
    session_id: int
    user_id: int


class RefreshTokenService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._ttl = timedelta(milliseconds=settings.jwt_refresh_ttl_ms)

    def create_refresh_token(self, user_id: int) -> RefreshTokenResult:
        user = self._session.get(User, user_id)
        if user is None:
            raise ApiException(ErrorCode.UNAUTHENTICATED)
        if not user.is_active:
            raise ApiException(ErrorCode.ACCOUNT_INACTIVE)

        now = utcnow()
        token = generate_token()
        row = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_token(token),
            expires_at=now + self._ttl,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return RefreshTokenResult(token, row.id, user.id)

    def rotate_refresh_token(self, token: str | None) -> RefreshTokenResult:
        if token is None or not token.strip():
            raise ApiException(ErrorCode.UNAUTHENTICATED)

        row = self._session.scalars(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == hash_token(token))
            .with_for_update()
        ).first()
        if row is None:
            raise ApiException(ErrorCode.UNAUTHENTICATED)

        now = utcnow()
        if row.revoked_at is not None or not row.expires_at > now:
            raise ApiException(ErrorCode.UNAUTHENTICATED)
        if row.user is None or not row.user.is_active:
            raise ApiException(ErrorCode.ACCOUNT_INACTIVE)

        replacement = generate_token()
        row.refresh_token_hash = hash_token(replacement)
        row.expires_at = now + self._ttl
        row.updated_at = now
        self._session.flush()
        return RefreshTokenResult(replacement, row.id, row.user_id)

    def revoke_refresh_token(self, token: str | None) -> None:
        if token is None or not token.strip():
            return
        row = self._session.scalars(
            select(AuthSession).where(AuthSession.refresh_token_hash == hash_token(token))
        ).first()
        if row is None or row.revoked_at is not None:
            return
        now = utcnow()
        row.revoked_at = now
        row.updated_at = now

    def revoke_all_for_user(self, user_id: int) -> None:
        now = utcnow()
        self._session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now, updated_at=now)
        )


class RefreshTokenCookieService:
    def __init__(self, settings: Settings) -> None:
        self._secure = settings.auth_cookie_secure
        self._same_site = settings.auth_cookie_same_site
        self._max_age = settings.jwt_refresh_ttl_ms // 1000

    def set_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=self._max_age,
            path=COOKIE_PATH,
            httponly=True,
            secure=self._secure,
            samesite=_starlette_same_site(self._same_site),
        )

    def clear_cookie(self, response: Response) -> None:
        response.set_cookie(
            key=COOKIE_NAME,
            value="",
            max_age=0,
            path=COOKIE_PATH,
            httponly=True,
            secure=self._secure,
            samesite=_starlette_same_site(self._same_site),
        )


def _starlette_same_site(value: str) -> str:
    normalized = (value or "lax").strip().lower()
    return normalized if normalized in {"lax", "strict", "none"} else "lax"
