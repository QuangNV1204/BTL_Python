"""Callback sau commit/rollback của một request, tương ứng TransactionSynchronization.

Session SQLAlchemy không phát sự kiện commit của tầng ứng dụng, nên tầng HTTP gọi
``run_after_commit``/``run_after_rollback`` sau khi commit/rollback transaction của
request. Java dùng cơ chế tương tự để chỉ xóa file sau khi metadata đã commit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

logger = logging.getLogger("learningai.tx")

_AFTER_COMMIT = "after_commit_callbacks"
_AFTER_ROLLBACK = "after_rollback_callbacks"


def after_commit(session: Session, callback: Callable[[], None]) -> None:
    session.info.setdefault(_AFTER_COMMIT, []).append(callback)


def after_rollback(session: Session, callback: Callable[[], None]) -> None:
    session.info.setdefault(_AFTER_ROLLBACK, []).append(callback)


def run_after_commit(session: Session) -> None:
    callbacks = session.info.pop(_AFTER_COMMIT, [])
    for callback in callbacks:
        try:
            callback()
        except Exception:  # noqa: BLE001 - lỗi dọn dẹp không được làm hỏng response
            logger.error("after-commit callback failed", exc_info=True)


def run_after_rollback(session: Session) -> None:
    callbacks = session.info.pop(_AFTER_ROLLBACK, [])
    session.info.pop(_AFTER_COMMIT, None)
    for callback in callbacks:
        try:
            callback()
        except Exception:  # noqa: BLE001
            logger.error("after-rollback callback failed", exc_info=True)
