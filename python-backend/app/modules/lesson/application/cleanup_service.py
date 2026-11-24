
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.database.dialect import insert_ignore, utc_timestamp_now
from app.shared.database.hooks import after_commit, after_rollback
from app.shared.database.locking import select_for_update
from app.shared.database.session import SessionLocal, independent_session
from app.shared.storage.documents import DocumentStorage

logger = logging.getLogger("learningai.cleanup")


class DocumentCleanupService:
    def __init__(self, session: Session, storage: DocumentStorage) -> None:
        self._session = session
        self._storage = storage
        self._staged: set[str] = set()

    def after_commit(self, storage_key: str) -> None:
        self._session.execute(
            insert_ignore("document_cleanup_jobs", "storage_key", ":key"),
            {"key": storage_key},
        )
        after_commit(self._session, lambda key=storage_key: _cleanup(key, self._storage))

    def stage_upload(self, storage_key: str) -> None:
        with independent_session() as session:
            session.execute(
                text(
                    "INSERT INTO document_cleanup_jobs(storage_key, job_type) "
                    "VALUES (:key, 'STAGING')"
                ),
                {"key": storage_key},
            )
        row = self._session.execute(
            select_for_update(
                "SELECT storage_key FROM document_cleanup_jobs WHERE storage_key = :key"
            ),
            {"key": storage_key},
        ).first()
        if row is None:
            raise IllegalUploadStaging()
        self._staged.add(storage_key)
        after_rollback(self._session, lambda key=storage_key: self._rollback_one(key))

    def adopt_upload(self, storage_key: str) -> None:
        self._session.execute(
            text("DELETE FROM document_cleanup_jobs WHERE storage_key = :key"),
            {"key": storage_key},
        )
        self._staged.discard(storage_key)

    def _rollback_one(self, storage_key: str) -> None:
        try:
            self._storage.delete(storage_key)
        except Exception:
            logger.error("Could not delete staged upload %s", storage_key, exc_info=True)
        with independent_session() as session:
            session.execute(
                text("DELETE FROM document_cleanup_jobs WHERE storage_key = :key"),
                {"key": storage_key},
            )
        self._staged.discard(storage_key)


class IllegalUploadStaging(Exception):
    pass


def retry_pending(storage: DocumentStorage, limit: int = 100) -> None:
    with SessionLocal() as session:
        keys = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT storage_key FROM document_cleanup_jobs "
                    "ORDER BY checked_at, storage_key LIMIT :limit"
                ),
                {"limit": limit},
            )
        ]
    for key in keys:
        _cleanup(key, storage)


def _cleanup(storage_key: str, storage: DocumentStorage) -> None:
    try:
        with independent_session() as session:
            job_type = session.execute(
                select_for_update(
                    "SELECT job_type FROM document_cleanup_jobs WHERE storage_key = :key",
                    skip_locked=True,
                ),
                {"key": storage_key},
            ).scalar()
            if job_type is None:
                return
            adopted = bool(
                session.execute(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM lesson_documents WHERE storage_key = :key)"
                    ),
                    {"key": storage_key},
                ).scalar()
            )
            if not adopted:

                try:
                    storage.delete(storage_key)
                except Exception:
                    logger.warning("Could not delete document %s", storage_key, exc_info=True)
            if adopted or job_type == "DELETE":
                session.execute(
                    text("DELETE FROM document_cleanup_jobs WHERE storage_key = :key"),
                    {"key": storage_key},
                )
            else:

                session.execute(
                    text(
                        "UPDATE document_cleanup_jobs SET checked_at = "
                        f"{utc_timestamp_now()} WHERE storage_key = :key"
                    ),
                    {"key": storage_key},
                )
    except Exception:
        logger.error("Document cleanup failed; durable job retained for retry", exc_info=True)
