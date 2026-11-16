"""Khai báo Base và kiểu thời gian dùng chung.

MySQL DATETIME(6) không có timezone. java-backend ghi Instant theo UTC, nên toàn bộ
giá trị trong DB là UTC "naive". Tầng này giữ nguyên quy ước đó: nhận/trả datetime
naive UTC, serialize ra ISO-8601 có hậu tố Z ở tầng HTTP.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

# MySQL dùng BIGINT AUTO_INCREMENT; SQLite chỉ tự tăng với INTEGER PRIMARY KEY,
# nên bản test SQLite dùng đúng kiểu đó. Production luôn là BIGINT.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


def utcnow() -> datetime:
    """Thời điểm hiện tại, naive UTC, độ chính xác microsecond (DATETIME(6))."""
    return datetime.now(UTC).replace(tzinfo=None)


class UTCDateTime(TypeDecorator):
    """DATETIME(6) <-> datetime naive UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):  # noqa: ANN001
        return value


class Base(DeclarativeBase):
    pass
