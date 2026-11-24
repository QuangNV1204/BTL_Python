
from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-Id"
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

_current_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def resolve_request_id(supplied: str | None) -> str:
    if supplied is not None and _SAFE_ID.fullmatch(supplied):
        return supplied
    return str(uuid.uuid4())


def set_request_id(value: str) -> None:
    _current_request_id.set(value)


def current_request_id() -> str | None:
    return _current_request_id.get()
