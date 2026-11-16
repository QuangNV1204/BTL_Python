"""Router AI — khớp AiController.java (chỉ TEACHER/ADMIN, owner của lesson do service kiểm)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.modules.ai.application.generation_service import (
    AiGenerationService,
    GenerationRequest,
)
from app.modules.lesson.application.access_policy import LessonAccessPolicy
from app.modules.lesson.application.lesson_service import LessonService
from app.shared.auth.principal import AuthenticatedUser
from app.shared.config.settings import get_settings
from app.shared.domain.enums import Difficulty, SourceType
from app.shared.http.dependencies import get_db, require_teacher_or_admin

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class GenerationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: int
    source_type: SourceType
    document_id: int | None = None
    count: int = Field(ge=1, le=10)
    difficulty: Difficulty | None = None


def _service(request: Request, session: Session = Depends(get_db)) -> AiGenerationService:
    settings = get_settings()
    policy = LessonAccessPolicy(session)
    lessons = LessonService(
        session, settings, request.app.state.document_storage, policy
    )
    return AiGenerationService(
        session, settings, request.app.state.ai_client, policy, lessons
    )


Service = Annotated[AiGenerationService, Depends(_service)]


@router.post("/generate-quiz")
def generate_quiz(
    payload: GenerationBody,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> dict:
    return service.generate_quiz(actor.user_id, _to_request(payload))


@router.post("/generate-flashcards")
def generate_flashcards(
    payload: GenerationBody,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> dict:
    return service.generate_flashcards(actor.user_id, _to_request(payload))


def _to_request(payload: GenerationBody) -> GenerationRequest:
    return GenerationRequest(
        lesson_id=payload.lesson_id,
        source_type=payload.source_type,
        document_id=payload.document_id,
        count=payload.count,
        difficulty=payload.difficulty,
    )
