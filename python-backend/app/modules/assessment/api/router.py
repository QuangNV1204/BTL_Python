
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.modules.assessment.api.schemas import (
    CreateQuizRequest,
    QuizAuthorResponse,
    QuizPublicationRequest,
    SaveQuizDraftRequest,
    UpdateQuizRequest,
    WriteQuestionRequest,
)
from app.modules.assessment.application.draft_save_service import QuizDraftSaveService
from app.modules.assessment.application.quiz_service import QuizService
from app.modules.lesson.application.access_policy import LessonAccessPolicy
from app.shared.auth.principal import AuthenticatedUser, principal_of
from app.shared.http.dependencies import get_db, require_teacher_or_admin
from app.shared.validation.validators import parse_positive_id, parse_positive_int

router = APIRouter(prefix="/api/v1", tags=["assessment"])


def _policy(session: Session = Depends(get_db)) -> LessonAccessPolicy:
    return LessonAccessPolicy(session)


def _service(policy: LessonAccessPolicy = Depends(_policy)) -> QuizService:
    return QuizService(_session_of(policy), policy)


def _session_of(policy: LessonAccessPolicy) -> Session:
    return policy._session


Service = Annotated[QuizService, Depends(_service)]


def _draft_service(service: Service) -> QuizDraftSaveService:
    return QuizDraftSaveService(_session_of(service._policy), service)


DraftService = Annotated[QuizDraftSaveService, Depends(_draft_service)]


@router.post(
    "/lessons/{lesson_id}/quizzes",
    status_code=status.HTTP_201_CREATED,
    response_model=QuizAuthorResponse,
)
def create_quiz(
    lesson_id: str,
    response: Response,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
    body: Any = Body(...),
) -> QuizAuthorResponse:
    parsed_lesson = parse_positive_id(lesson_id, "lesson_id")
    quiz = service.create(parsed_lesson, CreateQuizRequest.from_json(body), actor)
    response.headers["Location"] = f"/api/v1/quizzes/{quiz.id}"
    return quiz


@router.get("/lessons/{lesson_id}/quizzes")
def list_quizzes(
    lesson_id: str,
    request: Request,
    service: Service,
    page: str = Query(default="1"),
    page_size: str = Query(default="20"),
) -> dict:
    return service.list(
        parse_positive_id(lesson_id, "lesson_id"),
        principal_of(request),
        parse_positive_int(page, "page"),
        parse_positive_int(page_size, "page_size"),
    )


@router.get("/quizzes/{quiz_id}")
def get_quiz(
    quiz_id: str, request: Request, service: Service
) -> QuizAuthorResponse | dict:
    result = service.get(parse_positive_id(quiz_id, "quiz_id"), principal_of(request))
    return result.model_dump(mode="json")


@router.patch("/quizzes/{quiz_id}", response_model=QuizAuthorResponse)
def update_quiz(
    quiz_id: str,
    response: Response,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
    body: Any = Body(...),
) -> QuizAuthorResponse:
    return service.update(
        parse_positive_id(quiz_id, "quiz_id"), UpdateQuizRequest.from_json(body), actor
    )


@router.delete("/quizzes/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(
    quiz_id: str,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> Response:
    service.delete(parse_positive_id(quiz_id, "quiz_id"), actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/quizzes/{quiz_id}/publication", response_model=QuizAuthorResponse)
def change_publication(
    quiz_id: str,
    response: Response,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
    body: Any = Body(...),
) -> QuizAuthorResponse:
    return service.change_publication(
        parse_positive_id(quiz_id, "quiz_id"),
        QuizPublicationRequest.from_json(body),
        actor,
    )


@router.post("/quizzes/{quiz_id}/questions", status_code=status.HTTP_201_CREATED)
def add_question(
    quiz_id: str,
    response: Response,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
    body: Any = Body(...),
) -> dict:
    question = service.add_question(
        parse_positive_id(quiz_id, "quiz_id"),
        WriteQuestionRequest.from_json(body),
        actor,
    )
    response.headers["Location"] = f"/api/v1/questions/{question.id}"
    return question.model_dump(mode="json")


@router.put("/questions/{question_id}")
def replace_question(
    question_id: str,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
    body: Any = Body(...),
) -> dict:
    question = service.replace_question(
        parse_positive_id(question_id, "question_id"),
        WriteQuestionRequest.from_json(body),
        actor,
    )
    return question.model_dump(mode="json")


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: str,
    service: Service,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
) -> Response:
    service.delete_question(parse_positive_id(question_id, "question_id"), actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/quizzes/{quiz_id}/draft", response_model=QuizAuthorResponse)
def save_draft(
    quiz_id: str,
    service: DraftService,
    actor: AuthenticatedUser = Depends(require_teacher_or_admin),
    body: Any = Body(...),
) -> QuizAuthorResponse:
    return service.save(parse_positive_id(quiz_id, "quiz_id"), SaveQuizDraftRequest.from_json(body), actor)
