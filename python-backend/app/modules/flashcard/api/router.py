
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.modules.ai.application.generation_service import AiGenerationService
from app.modules.flashcard.api.schemas import (
    CardResponse,
    CardUpdateRequest,
    CardWriteRequest,
    StatusRequest,
)
from app.modules.flashcard.application.flashcard_service import FlashcardService
from app.modules.lesson.api.router import lesson_service
from app.modules.lesson.application.access_policy import LessonAccessPolicy
from app.shared.auth.principal import AuthenticatedUser, principal_of
from app.shared.config.settings import get_settings
from app.shared.http.dependencies import get_db, require_teacher_or_admin

router = APIRouter(prefix="/api/v1", tags=["flashcard"])


def _service(request: Request, session: Session = Depends(get_db)) -> FlashcardService:
    settings = get_settings()
    policy = LessonAccessPolicy(session)
    lessons = lesson_service(request, session)
    ai = AiGenerationService(
        session, settings, request.app.state.ai_client, policy, lessons
    )
    return FlashcardService(session, policy, ai)


Service = Annotated[FlashcardService, Depends(_service)]


@router.get("/lessons/{lesson_id}/flashcards")
def list_flashcards(
    lesson_id: int,
    request: Request,
    service: Service,
    page: int = Query(default=1),
    page_size: int = Query(default=20),
) -> dict:
    return service.list_flashcards(lesson_id, principal_of(request).user_id, page, page_size)


@router.post(
    "/lessons/{lesson_id}/flashcards",
    status_code=status.HTTP_201_CREATED,
    response_model=CardResponse,
)
def create_flashcard(
    lesson_id: int,
    payload: CardWriteRequest,
    response: Response,
    request: Request,
    service: Service,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> CardResponse:
    card = service.save_draft(lesson_id, principal_of(request).user_id, payload)
    response.headers["Location"] = f"/api/v1/flashcards/{card.id}"
    return card


@router.patch("/flashcards/{card_id}", response_model=CardResponse)
def update_flashcard(
    card_id: int,
    payload: CardUpdateRequest,
    request: Request,
    service: Service,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> CardResponse:
    return service.update_draft(card_id, principal_of(request).user_id, payload)


@router.delete("/flashcards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flashcard(
    card_id: int,
    request: Request,
    service: Service,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> Response:
    service.delete_draft(card_id, principal_of(request).user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/flashcards/{card_id}/publication", response_model=CardResponse)
def publish_flashcard(
    card_id: int,
    payload: StatusRequest,
    request: Request,
    service: Service,
    _: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> CardResponse:
    return service.change_status(card_id, principal_of(request).user_id, payload.status)
