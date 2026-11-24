
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import jwt
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.shared.auth.jwt_service import JwtService
from app.shared.auth.principal import AuthenticatedUser
from app.shared.database.models import User
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.http.errors import api_error_response

logger = logging.getLogger("learningai.auth")


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, jwt_service: JwtService, session_factory) -> None:
        super().__init__(app)
        self._jwt = jwt_service
        self._session_factory = session_factory

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        header = request.headers.get("Authorization")
        request.state.principal = None
        if header is None or not header.startswith("Bearer "):
            return await call_next(request)

        token = header[len("Bearer ") :]
        try:
            email = self._jwt.extract_username(token)
        except jwt.PyJWTError as exc:
            logger.info("Invalid access token: %s", exc)
            return await call_next(request)

        if email is None:
            return await call_next(request)

        session = self._session_factory()
        try:
            user = session.scalars(select(User).where(User.email == email)).first()
        finally:
            session.close()

        if user is None:
            logger.info("Access token references a missing user: %s", email)
            return await call_next(request)

        if not user.is_active:
            return api_error_response(ApiException(ErrorCode.ACCOUNT_INACTIVE))

        request.state.principal = AuthenticatedUser.build(user)
        return await call_next(request)
