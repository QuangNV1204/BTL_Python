
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

    if text.endswith(".000000"):
        text = text[: -len(".000000")]
    elif text.endswith("000"):
        text = text.rstrip("0").rstrip(".") if "." in text else text
    return text + "Z"


def serialize_id(value: int | None) -> str | None:
    return None if value is None else str(value)


def serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:.2f}"


def serialize_number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


Instant = Annotated[datetime, PlainSerializer(format_instant, return_type=str | None)]
IdStr = Annotated[str, PlainSerializer(lambda v: v, return_type=str)]
PriceStr = Annotated[Decimal, PlainSerializer(serialize_decimal, return_type=str | None)]
ScoreNumber = Annotated[Decimal, PlainSerializer(serialize_number, return_type=float | None)]


class ApiModel(BaseModel):

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class OutModel(BaseModel):

    model_config = ConfigDict(extra="forbid", populate_by_name=True, ser_json_timedelta="float")


def jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value
