"""Kiểu serialize theo contracts/api-conventions.md.

- BIGINT trên wire là **string** (không mất độ chính xác ở frontend).
- price là decimal string; score là number.
- Timestamp ISO-8601 UTC có hậu tố ``Z`` (Java serialize Instant như vậy).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, PlainSerializer


def format_instant(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    text = value.isoformat(timespec="microseconds")
    # Bỏ phần lẻ bằng 0 cho gần với Jackson (không lúc nào in .000000).
    if text.endswith(".000000"):
        text = text[: -len(".000000")]
    elif text.endswith("000"):
        text = text.rstrip("0").rstrip(".") if "." in text else text
    return text + "Z"


def serialize_id(value: int | None) -> str | None:
    return None if value is None else str(value)


def serialize_decimal(value: Decimal | None) -> str | None:
    """price: luôn 2 chữ số thập phân như DECIMAL(14,2)."""
    if value is None:
        return None
    return f"{value:.2f}"


def serialize_number(value: Decimal | None) -> float | None:
    """score/completion_rate: number thang 0–100."""
    return None if value is None else float(value)


Instant = Annotated[datetime, PlainSerializer(format_instant, return_type=str | None)]
IdStr = Annotated[str, PlainSerializer(lambda v: v, return_type=str)]
PriceStr = Annotated[Decimal, PlainSerializer(serialize_decimal, return_type=str | None)]
ScoreNumber = Annotated[Decimal, PlainSerializer(serialize_number, return_type=float | None)]


class ApiModel(BaseModel):
    """Base cho response/request: không tự thêm field lạ, không đổi tên field."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class OutModel(BaseModel):
    """Base cho response để dễ đổi cấu hình riêng nếu cần."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, ser_json_timedelta="float")


def jsonable(value: Any) -> Any:
    """Chuyển pydantic model/dataclass sang JSON dict đã áp quy ước wire."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value
