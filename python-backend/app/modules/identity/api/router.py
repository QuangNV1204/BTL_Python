
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.modules.identity.api.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    CreateTeacherRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResendVerificationEmailRequest,
    ResetPasswordRequest,
    TeacherDecisionRequest,
    TeacherRequestResponse,
    UpdateProfileRequest,
    UpdateUserStatusRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.modules.identity.application.auth_service import AuthService
from app.modules.identity.application.email_verification_service import (
    EmailVerificationService,
)
from app.modules.identity.application.password_reset_service import PasswordResetService
from app.modules.identity.application.teacher_request_service import (
    TeacherRequestService,
)
from app.modules.identity.application.user_service import UserService
from app.shared.auth.jwt_service import JwtService
from app.shared.auth.principal import AuthenticatedUser, principal_of
from app.shared.auth.refresh_tokens import (
    COOKIE_NAME,
    RefreshTokenCookieService,
    RefreshTokenService,
)
from app.shared.config.settings import Settings, get_settings
from app.shared.http.dependencies import (
    get_db,
    require_admin,
    require_student,
)
from app.shared.mail.email_service import EmailService
from app.shared.pagination import page_response

router = APIRouter(prefix="/api/v1", tags=["identity"])


@dataclass
class _Identity:

    auth: AuthService
    email_verification: EmailVerificationService
    password_reset: PasswordResetService
    teacher_requests: TeacherRequestService
    users: UserService
    cookies: RefreshTokenCookieService


def _services(request: Request, session: Session = Depends(get_db)) -> _Identity:
    settings: Settings = get_settings()
    jwt_service: JwtService = request.app.state.jwt_service
    refresh = RefreshTokenService(session, settings)
    mail = EmailService(settings)
    email_verification = EmailVerificationService(session, mail)
    teacher_requests = TeacherRequestService(session)
    return _Identity(
        auth=AuthService(session, jwt_service, refresh, email_verification, teacher_requests),
        email_verification=email_verification,
        password_reset=PasswordResetService(session, mail, refresh),
        teacher_requests=teacher_requests,
        users=UserService(session, refresh),
        cookies=RefreshTokenCookieService(settings),
    )


Identity = Annotated[_Identity, Depends(_services)]


@router.post(
    "/auth/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
)
def register(payload: RegisterRequest, services: Identity) -> UserResponse:
    return services.auth.register(payload)


@router.post("/auth/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(payload: VerifyEmailRequest, services: Identity) -> Response:
    services.email_verification.verify_email(payload.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
def resend_verification(
    payload: ResendVerificationEmailRequest, services: Identity
) -> Response:
    services.email_verification.resend_verification_email(payload.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(payload: ForgotPasswordRequest, services: Identity) -> Response:
    services.password_reset.forgot_password(payload.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    payload: ResetPasswordRequest, services: Identity, response: Response
) -> Response:
    services.password_reset.reset_password(payload)
    services.cookies.clear_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, services: Identity, response: Response) -> AuthResponse:
    result = services.auth.login(payload)
    services.cookies.set_cookie(response, result.refresh_token)
    return AuthResponse(access_token=result.access_token)


@router.post("/auth/refresh", response_model=AuthResponse)
def refresh_token(
    request: Request, services: Identity, response: Response
) -> AuthResponse:
    result = services.auth.refresh_token(request.cookies.get(COOKIE_NAME))
    services.cookies.set_cookie(response, result.refresh_token)
    return AuthResponse(access_token=result.access_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, services: Identity, response: Response) -> Response:
    services.auth.logout(request.cookies.get(COOKIE_NAME))
    services.cookies.clear_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest, request: Request, services: Identity
) -> Response:
    services.auth.change_password(principal_of(request), payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(request: Request, services: Identity, response: Response) -> Response:
    services.auth.logout_all(principal_of(request))
    services.cookies.clear_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/users/me", response_model=UserResponse)
def get_current_user(
    request: Request, services: Identity
) -> UserResponse:
    return services.users.get_current_user(principal_of(request))


@router.patch("/users/me", response_model=UserResponse)
def update_profile(
    payload: UpdateProfileRequest, request: Request, services: Identity
) -> UserResponse:
    return services.users.update_profile(principal_of(request), payload)


@router.patch("/users/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: int,
    payload: UpdateUserStatusRequest,
    services: Identity,
    _: AuthenticatedUser = Depends(require_admin),
) -> UserResponse:
    return services.users.update_user_status(user_id, payload)


@router.get("/users")
def get_users(
    services: Identity,
    email: str | None = Query(default=None),
    page: int = Query(default=1),
    page_size: int = Query(default=10),
    sort: str | None = Query(default=None),
    _: AuthenticatedUser = Depends(require_admin),
) -> dict:
    return services.users.get_users(email, page, page_size, sort)


@router.post(
    "/teacher-requests",
    status_code=status.HTTP_201_CREATED,
    response_model=TeacherRequestResponse,
)
def create_teacher_request(
    payload: CreateTeacherRequest,
    services: Identity,
    principal: AuthenticatedUser = Depends(require_student),
) -> TeacherRequestResponse:
    return services.teacher_requests.create(principal.user_id, payload)


@router.get("/teacher-requests/me")
def get_my_teacher_requests(
    request: Request,
    services: Identity,
    page: int = Query(default=1),
    page_size: int = Query(default=10),
    sort: str | None = Query(default=None),
) -> dict:
    return services.teacher_requests.get_mine(
        principal_of(request).user_id, page, page_size, sort
    )


@router.get("/teacher-requests")
def get_teacher_requests(
    services: Identity,
    teacher_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1),
    page_size: int = Query(default=10),
    sort: str | None = Query(default=None),
    _: AuthenticatedUser = Depends(require_admin),
) -> dict:
    from app.shared.domain.enums import TeacherRequestStatus

    parsed = None
    if teacher_status is not None:
        try:
            parsed = TeacherRequestStatus(teacher_status)
        except ValueError as exc:
            from app.shared.error.codes import ErrorCode
            from app.shared.error.exceptions import ApiException

            raise ApiException(
                ErrorCode.VALIDATION_ERROR, "Invalid request parameter"
            ) from exc
    return services.teacher_requests.get_requests(parsed, page, page_size, sort)


@router.patch("/teacher-requests/{request_id}/decision", response_model=TeacherRequestResponse)
def decide_teacher_request(
    request_id: int,
    payload: TeacherDecisionRequest,
    services: Identity,
    admin: AuthenticatedUser = Depends(require_admin),
) -> TeacherRequestResponse:
    return services.teacher_requests.decide(admin.user_id, request_id, payload)


__all__ = ["router", "page_response"]
