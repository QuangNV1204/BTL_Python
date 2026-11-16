"""Engine/Session SQLAlchemy và helper transaction độc lập.

Một request dùng một Session (xem app.shared.http.dependencies.get_db). Các thao
tác cần transaction riêng (staging tài liệu, cleanup) mở Session độc lập qua
``independent_session`` — tương đương PROPAGATION_REQUIRES_NEW của Spring.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.shared.config.settings import get_settings

_settings = get_settings()

# MySQL mặc định REPEATABLE READ. Các luồng ghi quan trọng của java-backend khai báo
# READ_COMMITTED; dùng thống nhất mức này để tránh đọc dữ liệu cũ trong transaction.
# SQLite (dùng cho test) chỉ hỗ trợ SERIALIZABLE nên bỏ qua tùy chọn này.
_url = _settings.sqlalchemy_url
_is_sqlite = _url.startswith("sqlite")

engine = create_engine(
    _url,
    pool_pre_ping=True,
    pool_recycle=1_800,
    **({} if _is_sqlite else {"isolation_level": "READ COMMITTED"}),
    future=True,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


@contextmanager
def independent_session() -> Iterator[Session]:
    """Session + transaction riêng, commit/rollback độc lập với request."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
