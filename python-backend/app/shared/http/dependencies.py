
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.shared.auth.principal import AuthenticatedUser, principal_of
from app.shared.config.settings import Settings, get_settings
from app.shared.database.models import User
from app.shared.database.session import SessionLocal
from app.shared.domain.enums import UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException


def get_db(request: Request) -> Iterator[Session]:
    from app.shared.database.hooks import run_after_commit, run_after_rollback

    session = SessionLocal()
    request.state.db = session
    try:
        yield session
        session.commit()
        run_after_commit(session)
    except Exception:
        session.rollback()
        run_after_rollback(session)
        raise
    finally:
        session.close()


def get_current_user(request: Request) -> AuthenticatedUser:
    return principal_of(request)


def get_settings_dep() -> Settings:
    return get_settings()


def require_roles(*roles: UserRole):

    def dependency(request: Request) -> AuthenticatedUser:
        principal = principal_of(request)
        if principal.role not in roles:
            raise ApiException(ErrorCode.FORBIDDEN)
        return principal

    return dependency


def require_teacher_or_admin(request: Request) -> AuthenticatedUser:
    principal = principal_of(request)
    if not principal.is_teacher_or_admin:
        raise ApiException(ErrorCode.FORBIDDEN)
    return principal


def require_student(request: Request) -> AuthenticatedUser:
    principal = principal_of(request)
    if principal.role is not UserRole.STUDENT:
        raise ApiException(ErrorCode.FORBIDDEN)
    return principal


def require_admin(request: Request) -> AuthenticatedUser:
    principal = principal_of(request)
    if not principal.is_admin:
        raise ApiException(ErrorCode.FORBIDDEN)
    return principal


def current_db_user(session: Session, principal: AuthenticatedUser) -> User:
    user = session.get(User, principal.user_id)
    if user is None:
        raise ApiException(ErrorCode.UNAUTHENTICATED)
    if not user.is_active:
        raise ApiException(ErrorCode.ACCOUNT_INACTIVE)
    return user
