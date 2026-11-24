
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.elements import TextClause

from app.shared.database.session import engine


def supports_row_locks(bind: Engine | None = None) -> bool:
    dialect = (bind or engine).dialect.name
    return dialect != "sqlite"


def select_for_update(sql: str, *, skip_locked: bool = False, bind: Engine | None = None) -> TextClause:
    if not supports_row_locks(bind):
        return text(sql)
    suffix = " FOR UPDATE SKIP LOCKED" if skip_locked else " FOR UPDATE"
    return text(sql + suffix)
