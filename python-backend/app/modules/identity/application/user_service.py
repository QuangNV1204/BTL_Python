"""Hồ sơ, khóa tài khoản và danh sách user — sao UserService.java."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.identity.api.schemas import (
    UpdateProfileRequest,
    UpdateUserStatusRequest,
    UserResponse,
    user_response,
)
from app.shared.auth.principal import AuthenticatedUser
from app.shared.auth.refresh_tokens import RefreshTokenService
from app.shared.database.base import utcnow
from app.shared.database.models import User
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.pagination import page_response, require_valid_pagination

_SORTABLE = {
    "full_name": User.full_name,
    "fullName": User.full_name,
    "is_active": User.is_active,
    "isActive": User.is_active,
    "created_at": User.created_at,
    "createdAt": User.created_at,
    "id": User.id,
    "email": User.email,
    "role": User.role,
}


class UserService:
    def __init__(self, session: Session, refresh_tokens: RefreshTokenService) -> None:
        self._session = session
        self._refresh_tokens = refresh_tokens

    def get_current_user(self, principal: AuthenticatedUser) -> UserResponse:
        user = self._session.get(User, principal.user_id)
        if user is None:
            raise ApiException(ErrorCode.UNAUTHENTICATED)
        if not user.is_active:
            raise ApiException(ErrorCode.ACCOUNT_INACTIVE)
        return user_response(user)

    def update_profile(
        self, principal: AuthenticatedUser, request: UpdateProfileRequest
    ) -> UserResponse:
        user = self._session.get(User, principal.user_id)
        if user is None:
            raise ApiException(ErrorCode.UNAUTHENTICATED)
        user.full_name = request.full_name
        user.updated_at = utcnow()
        self._session.flush()
        return user_response(user)

    def update_user_status(
        self, user_id: int, request: UpdateUserStatusRequest
    ) -> UserResponse:
        user = self._session.get(User, user_id)
        if user is None:
            raise ApiException(ErrorCode.NOT_FOUND, "User not found")
        user.is_active = request.is_active
        user.updated_at = utcnow()
        self._session.flush()
        if not request.is_active:
            self._refresh_tokens.revoke_all_for_user(user_id)
        return user_response(user)

    def get_users(
        self,
        email: str | None,
        page: int,
        page_size: int,
        sort: str | None,
    ) -> dict:
        require_valid_pagination(page, page_size)
        pattern: str | None = None
        if email is not None and email.strip():
            keyword = email.strip().lower()
            if len(keyword) > 254:
                raise ApiException.field_error(
                    "email", "Email search must not exceed 254 characters"
                )
            pattern = "%" + _escape_like(keyword) + "%"

        statement = select(User)
        count_statement = select(func.count()).select_from(User)
        if pattern is not None:
            condition = User.email.ilike(pattern, escape="!")
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)

        total = self._session.scalar(count_statement) or 0
        rows = self._session.scalars(
            statement.order_by(*_order_by(sort))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return page_response([user_response(row) for row in rows], page, page_size, total)


def _escape_like(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def _order_by(sort: str | None) -> tuple:
    if not sort:
        return (User.created_at.desc(), User.id.desc())
    parts = [part.strip() for part in sort.split(",") if part.strip()]
    clauses = []
    seen_id = False
    index = 0
    while index < len(parts):
        property_name = parts[index]
        direction = "desc"
        if index + 1 < len(parts) and parts[index + 1].lower() in {"asc", "desc"}:
            direction = parts[index + 1].lower()
            index += 1
        index += 1
        column = _SORTABLE.get(property_name)
        if column is None:
            raise ApiException(ErrorCode.VALIDATION_ERROR, "Unsupported sort field")
        clauses.append(column.asc() if direction == "asc" else column.desc())
        if property_name == "id":
            seen_id = True
    if not seen_id:
        clauses.append(User.id.desc())
    return tuple(clauses)
