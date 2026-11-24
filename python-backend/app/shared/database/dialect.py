
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

from app.shared.database.session import engine


def is_sqlite() -> bool:
    return engine.dialect.name == "sqlite"


def insert_ignore(table: str, columns: str, values: str) -> TextClause:
    keyword = "INSERT OR IGNORE" if is_sqlite() else "INSERT IGNORE"
    return text(f"{keyword} INTO {table}({columns}) VALUES({values})")


def utc_timestamp_now() -> str:
    return "CURRENT_TIMESTAMP" if is_sqlite() else "UTC_TIMESTAMP(6)"
