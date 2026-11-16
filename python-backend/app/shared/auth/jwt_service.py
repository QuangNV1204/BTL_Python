"""Phát và xác minh access token, tương thích JwtService.java.

Token HS256 với:
- ``sub`` = email người dùng
- ``role`` = danh sách authority dạng ``ROLE_<ROLE>``
- ``iat`` / ``exp`` tính bằng giây (jjwt ghi NumericDate)

``JWT_SIGNING_KEY`` là Base64 như Java (``Base64.getDecoder().decode``).
bcrypt: hash ``$2a$10$...`` của Spring dùng được trực tiếp với thư viện bcrypt.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from app.shared.config.settings import Settings
from app.shared.database.models import User
from app.shared.domain.enums import UserRole


class JwtService:
    ALGORITHM = "HS256"

    def __init__(self, settings: Settings) -> None:
        self._key = settings.signing_key_bytes
        self._access_ttl_ms = settings.jwt_access_ttl_ms

    def generate_token(self, user: User) -> str:
        now = datetime.now(UTC)
        expires = now + timedelta(milliseconds=self._access_ttl_ms)
        payload = {
            "sub": user.email,
            "role": [f"ROLE_{UserRole(user.role).value}"],
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        }
        return jwt.encode(payload, self._key, algorithm=self.ALGORITHM)

    def extract_username(self, token: str) -> str | None:
        """Trả subject; token sai/hết hạn thì ném jwt.PyJWTError như Java coi là lỗi."""
        payload = jwt.decode(token, self._key, algorithms=[self.ALGORITHM])
        subject = payload.get("sub")
        return subject if isinstance(subject, str) else None
