
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.modules.ai.api.router import router as ai_router
from app.modules.ai.infrastructure.factory import build_ai_client
from app.modules.assessment.api.router import router as assessment_router
from app.modules.catalog.api.router import router as catalog_router
from app.modules.course.api.file_router import router as file_router
from app.modules.course.api.router import router as course_router
from app.modules.enrollment.api.router import router as enrollment_router
from app.modules.flashcard.api.router import router as flashcard_router
from app.modules.identity.api.router import router as identity_router
from app.modules.learning.api.router import router as learning_router
from app.modules.lesson.api.router import router as lesson_router
from app.modules.lesson.application.cleanup_service import retry_pending
from app.modules.statistics.api.router import router as statistics_router
from app.shared.auth.jwt_service import JwtService
from app.shared.auth.middleware import AuthMiddleware
from app.shared.config.settings import get_settings
from app.shared.database.session import SessionLocal
from app.shared.http.errors import install_error_handlers
from app.shared.http.request_context import RequestIdMiddleware
from app.shared.storage.documents import DocumentStorage
from app.shared.storage.local_file_storage import LocalFileStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("learningai")


async def _cleanup_loop(interval_seconds: int) -> None:
    storage = DocumentStorage(get_settings())
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(retry_pending, storage)
        except Exception:
            logger.error("Document cleanup sweep failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    task: asyncio.Task | None = None
    if settings.cleanup_delay_ms > 0:
        task = asyncio.create_task(_cleanup_loop(max(settings.cleanup_delay_ms // 1000, 5)))
    yield
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Learning AI — Python backend",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )


    application.state.settings = settings
    application.state.jwt_service = JwtService(settings)
    application.state.ai_client = build_ai_client(settings)
    application.state.file_storage = LocalFileStorage(settings)
    application.state.document_storage = DocumentStorage(settings)

    install_error_handlers(application)

    application.add_middleware(
        AuthMiddleware,
        jwt_service=application.state.jwt_service,
        session_factory=SessionLocal,
    )
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    for module_router in (
        identity_router,
        catalog_router,
        course_router,
        enrollment_router,
        lesson_router,
        flashcard_router,
        ai_router,
        assessment_router,
        learning_router,
        statistics_router,
        file_router,
    ):
        application.include_router(module_router)

    @application.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return application


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=get_settings().server_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
