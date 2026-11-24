
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.identity.api.schemas import (
    CreateTeacherRequest,
    TeacherDecisionRequest,
    TeacherRequestResponse,
    teacher_request_response,
)
from app.shared.database.base import utcnow
from app.shared.database.models import TeacherRequest, User
from app.shared.domain.enums import TeacherRequestStatus, UserRole
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException
from app.shared.pagination import page_response, require_valid_pagination

_SORTABLE = {"created_at", "createdAt", "decided_at", "decidedAt", "id", "status"}


class TeacherRequestService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, user_id: int, request: CreateTeacherRequest) -> TeacherRequestResponse:
        user = self._session.get(User, user_id)
        if user is None:
            raise ApiException(ErrorCode.UNAUTHENTICATED)
        if user.role != UserRole.STUDENT.value:
            raise ApiException(ErrorCode.FORBIDDEN)

        pending = self._session.scalar(
            select(func.count())
            .select_from(TeacherRequest)
            .where(
                TeacherRequest.user_id == user.id,
                TeacherRequest.status == TeacherRequestStatus.PENDING.value,
            )
        )
        if pending:
            raise ApiException(
                ErrorCode.INVALID_STATE, "A pending teacher request already exists"
            )

        row = TeacherRequest(
            user_id=user.id,
            reason=request.reason,
            status=TeacherRequestStatus.PENDING.value,
            created_at=utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return teacher_request_response(row)

    def get_mine(
        self, user_id: int, page: int, page_size: int, sort: str | None
    ) -> dict:
        require_valid_pagination(page, page_size)
        order = _order_by(sort)
        total = self._session.scalar(
            select(func.count())
            .select_from(TeacherRequest)
            .where(TeacherRequest.user_id == user_id)
        )
        rows = self._session.scalars(
            select(TeacherRequest)
            .where(TeacherRequest.user_id == user_id)
            .order_by(*order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return page_response(
            [teacher_request_response(row) for row in rows], page, page_size, total or 0
        )

    def get_requests(
        self,
        status: TeacherRequestStatus | None,
        page: int,
        page_size: int,
        sort: str | None,
    ) -> dict:
        require_valid_pagination(page, page_size)
        order = _order_by(sort)
        statement = select(TeacherRequest)
        count_statement = select(func.count()).select_from(TeacherRequest)
        if status is not None:
            statement = statement.where(TeacherRequest.status == status.value)
            count_statement = count_statement.where(TeacherRequest.status == status.value)
        total = self._session.scalar(count_statement) or 0
        rows = self._session.scalars(
            statement.order_by(*order).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return page_response(
            [teacher_request_response(row) for row in rows], page, page_size, total
        )

    def decide(
        self, admin_id: int, request_id: int, request: TeacherDecisionRequest
    ) -> TeacherRequestResponse:
        if request.status is TeacherRequestStatus.PENDING:
            raise ApiException(
                ErrorCode.VALIDATION_ERROR, "Decision status must be APPROVED or REJECTED"
            )

        row = self._session.scalars(
            select(TeacherRequest).where(TeacherRequest.id == request_id).with_for_update()
        ).first()
        if row is None:
            raise ApiException(ErrorCode.NOT_FOUND, "Teacher request not found")
        if row.user_id == admin_id:
            raise ApiException(
                ErrorCode.FORBIDDEN, "You cannot decide your own teacher request"
            )
        if row.status != TeacherRequestStatus.PENDING.value:
            raise ApiException(
                ErrorCode.INVALID_STATE, "Teacher request has already been decided"
            )

        user = self._session.get(User, row.user_id)
        if user is None:
            raise ApiException(ErrorCode.NOT_FOUND, "User not found")

        if request.status is TeacherRequestStatus.APPROVED:
            if user.role != UserRole.STUDENT.value or not user.is_active:
                raise ApiException(
                    ErrorCode.INVALID_STATE, "Only an active student can become a teacher"
                )
            user.role = UserRole.TEACHER.value
            user.updated_at = utcnow()

        now = utcnow()
        row.status = request.status.value
        row.decided_by = admin_id
        row.decision_note = request.decision_note
        row.decided_at = now
        self._session.flush()
        return teacher_request_response(row)


def _order_by(sort: str | None) -> tuple:
    mapping = {
        "created_at": TeacherRequest.created_at,
        "createdAt": TeacherRequest.created_at,
        "decided_at": TeacherRequest.decided_at,
        "decidedAt": TeacherRequest.decided_at,
        "id": TeacherRequest.id,
        "status": TeacherRequest.status,
    }
    if not sort:
        return (TeacherRequest.created_at.desc(), TeacherRequest.id.desc())


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
        if property_name not in mapping:
            raise ApiException(ErrorCode.VALIDATION_ERROR, "Unsupported sort field")
        column = mapping[property_name]
        clauses.append(column.asc() if direction == "asc" else column.desc())
        if property_name == "id":
            seen_id = True
    if not seen_id:
        clauses.append(TeacherRequest.id.desc())
    return tuple(clauses)


__all__ = ["TeacherRequestService"]
