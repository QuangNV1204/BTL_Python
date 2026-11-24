
from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from app.shared.auth.jwt_service import JwtService
from app.shared.auth.refresh_tokens import COOKIE_NAME, hash_token
from app.shared.config.settings import Settings

JAVA_TEST_KEY = "dGVzdC1vbmx5LXNpZ25pbmctbWF0ZXJpYWwtMzJieXRlcyEh"


def _settings() -> Settings:
    return Settings(jwt_signing_key=JAVA_TEST_KEY, database_url="sqlite+pysqlite:///:memory:")


def test_signing_key_is_base64_decoded_like_java() -> None:
    assert base64.b64decode(JAVA_TEST_KEY) == _settings().signing_key_bytes


def test_generated_token_has_java_claims() -> None:
    from app.shared.database.models import User

    service = JwtService(_settings())
    user = User(
        id=1,
        email="a@example.com",
        full_name="A",
        password_hash="x",
        role="TEACHER",
        is_active=True,
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    token = service.generate_token(user)
    payload = pyjwt.decode(token, service._key, algorithms=["HS256"])
    assert payload["sub"] == "a@example.com"
    assert payload["role"] == ["ROLE_TEACHER"]
    assert isinstance(payload["iat"], int) and isinstance(payload["exp"], int)
    assert payload["exp"] - payload["iat"] == 900


def test_expired_token_is_rejected() -> None:
    service = JwtService(_settings())
    past = datetime.now(UTC) - timedelta(minutes=5)
    token = pyjwt.encode(
        {"sub": "a@example.com", "role": ["ROLE_STUDENT"], "exp": past},
        service._key,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.PyJWTError):
        service.extract_username(token)


def test_refresh_token_matches_java_dto_pattern() -> None:
    import re

    from app.shared.auth.refresh_tokens import generate_token

    token = generate_token()
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    assert hash_token(token) == hash_token(token)
    assert len(hash_token(token)) == 64


def test_refresh_cookie_attributes(client) -> None:
    from app.shared.database.session import SessionLocal
    from tests.conftest import make_user

    with SessionLocal() as db:
        make_user(db, email="cookie@example.com")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "cookie@example.com", "password": "password1234"},
    )
    cookie_header = response.headers["set-cookie"]
    assert COOKIE_NAME in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Path=/api/v1/auth" in cookie_header
    assert "Max-Age=604800" in cookie_header

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]


    again = client.post("/api/v1/auth/refresh")
    assert again.status_code == 401


def test_login_is_case_insensitive_on_email(client) -> None:
    from app.shared.database.session import SessionLocal
    from tests.conftest import make_user

    with SessionLocal() as db:
        make_user(db, email="mixed@example.com")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "  MiXeD@Example.COM ", "password": "password1234"},
    )
    assert response.status_code == 200
