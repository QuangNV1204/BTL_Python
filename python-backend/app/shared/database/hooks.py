
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
        except Exception:
            logger.error("after-commit callback failed", exc_info=True)


def run_after_rollback(session: Session) -> None:
    callbacks = session.info.pop(_AFTER_ROLLBACK, [])
    session.info.pop(_AFTER_COMMIT, None)
    for callback in callbacks:
        try:
            callback()
        except Exception:
            logger.error("after-rollback callback failed", exc_info=True)
