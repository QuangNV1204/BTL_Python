"""Hàng đợi xóa file tài liệu — sao DocumentCleanupService.java.

Bảng ``document_cleanup_jobs`` (V7/V8) giữ job bền vững để việc xóa file không mất
khi metadata commit/rollback. Logic giữ nguyên:

- ``after_commit``: ghi job DELETE trong transaction hiện tại, xóa file sau commit.
- ``stage_upload``: ghi tombstone STAGING trong transaction RIÊNG (đã commit) trước
  khi ghi bytes, rồi khóa hàng bằng ``FOR UPDATE`` trên transaction của request để
  worker SKIP LOCKED bỏ qua file đang upload. Nếu request rollback, hook đã đăng ký
  sẽ xóa file và tombstone.
- ``adopt_upload``: xóa tombstone cùng transaction với metadata mới.
- ``retry_pending``: quét định kỳ, SKIP LOCKED để writer chậm không chặn batch.
"""

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
        """Ghi intent bền vững TRƯỚC khi ghi bytes; DB lỗi thì upload dừng.

        Insert chạy trong transaction riêng (đã commit), còn khóa hàng ``FOR UPDATE``
        chạy trên transaction của request — nhờ vậy worker SKIP LOCKED bỏ qua file
        đang upload cho tới khi metadata commit/rollback, giống Java.
        """
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
        """Xóa tombstone cùng transaction với metadata mới (crash thì cả hai rollback)."""
        self._session.execute(
            text("DELETE FROM document_cleanup_jobs WHERE storage_key = :key"),
            {"key": storage_key},
        )
        self._staged.discard(storage_key)

    def _rollback_one(self, storage_key: str) -> None:
        try:
            self._storage.delete(storage_key)
        except Exception:  # noqa: BLE001
            logger.error("Could not delete staged upload %s", storage_key, exc_info=True)
        with independent_session() as session:
            session.execute(
                text("DELETE FROM document_cleanup_jobs WHERE storage_key = :key"),
                {"key": storage_key},
            )
        self._staged.discard(storage_key)


class IllegalUploadStaging(Exception):
    """Upload staging bị thu hồi; client cần thử upload lại."""


def retry_pending(storage: DocumentStorage, limit: int = 100) -> None:
    """Tương ứng @Scheduled retryPending."""
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
                # UUID key không bao giờ dùng lại; xóa idempotent.
                try:
                    storage.delete(storage_key)
                except Exception:  # noqa: BLE001 - file có thể đã biến mất
                    logger.warning("Could not delete document %s", storage_key, exc_info=True)
            if adopted or job_type == "DELETE":
                session.execute(
                    text("DELETE FROM document_cleanup_jobs WHERE storage_key = :key"),
                    {"key": storage_key},
                )
            else:
                # Giữ tombstone: writer mất khóa DB có thể ghi file sau đó.
                session.execute(
                    text(
                        "UPDATE document_cleanup_jobs SET checked_at = "
                        f"{utc_timestamp_now()} WHERE storage_key = :key"
                    ),
                    {"key": storage_key},
                )
    except Exception:  # noqa: BLE001
        logger.error("Document cleanup failed; durable job retained for retry", exc_info=True)
