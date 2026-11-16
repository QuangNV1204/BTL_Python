"""Entry point FastAPI — tương đương LearningaiApplication + SecurityConfig.

Chạy: ``uvicorn app.main:app --port 8080`` (hoặc ``python -m app.main``).
Cùng route, cùng mã lỗi, cùng contract JSON với java-backend.
"""

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
    """Quét document_cleanup_jobs định kỳ (DocumentCleanupService.retryPending)."""
    storage = DocumentStorage(get_settings())
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(retry_pending, storage)
        except Exception:  # noqa: BLE001 - job nền không được chết
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

    # Tài nguyên dùng chung cho mọi request (thay cho bean của Spring).
    application.state.settings = settings
    application.state.jwt_service = JwtService(settings)
    application.state.ai_client = build_ai_client(settings)
    application.state.file_storage = LocalFileStorage(settings)
    application.state.document_storage = DocumentStorage(settings)

    install_error_handlers(application)
    # Thứ tự middleware: request id ngoài cùng để mọi lỗi đều có header.
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
        """Gốc không phải API: chuyển tới tài liệu để mở nhầm không bị 404."""
        return RedirectResponse(url="/docs")

    return application


app = create_app()


def main() -> None:
    """Entry point cho ``learningai`` / ``python -m app.main``."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # noqa: S104 - chạy trong container/dev
        port=get_settings().server_port,
        reload=False,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
