"""Validator Pydantic sao hành vi Jakarta Validation của java-backend.

Field name trả về trong ``details`` là snake_case như trên wire — Java đã đổi
tên field qua PropertyNamingStrategy trước khi trả lỗi.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from pydantic import BeforeValidator

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}


def is_youtube_url(value: str) -> bool:
    """Sao YouTubeUrlValidator.java: chỉ chấp nhận link YouTube hợp lệ."""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return False
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower()
    path = parts.path or ""
    if host == "youtu.be":
        return _has_value_after(path, "/")
    if host not in _YOUTUBE_HOSTS:
        return False
    if path == "/watch":
        params = parse_qs(parts.query)
        video = (params.get("v") or [""])[0]
        return bool(video.strip())
    return _has_value_after(path, "/embed/") or _has_value_after(path, "/shorts/")


def _has_value_after(path: str, prefix: str) -> bool:
    return path.startswith(prefix) and bool(path[len(prefix) :].strip())


def codepoint_length(value: str) -> int:
    """Số code point như ``String.codePointCount`` (emoji tính là 1)."""
    return len(value)


def truncate_to_codepoints(value: str, limit: int) -> str:
    """Cắt theo code point; không cắt đôi cặp surrogate như AiGenerationService.truncate."""
    if len(value) <= limit:
        return value
    return value[:limit]


def normalize_optional_text(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def parse_positive_id(value: str, field_name: str) -> int:
    """Path param BIGINT dạng string, sao ``positiveLong`` của controller Java."""
    from app.shared.error.codes import ErrorCode
    from app.shared.error.exceptions import ApiException

    if not isinstance(value, str) or not _positive_bigint(value):
        raise ApiException(
            ErrorCode.VALIDATION_ERROR, f"{field_name} must be a positive BIGINT"
        )
    number = int(value)
    if number > 2**63 - 1:
        raise ApiException(
            ErrorCode.VALIDATION_ERROR, f"{field_name} exceeds the signed BIGINT range"
        )
    return number


def _positive_bigint(value: str) -> bool:
    import re

    return re.fullmatch(r"[1-9][0-9]{0,18}", value) is not None


def parse_positive_int(value: str, field_name: str) -> int:
    number = parse_positive_id(value, field_name)
    if number > 2**31 - 1:
        from app.shared.error.codes import ErrorCode
        from app.shared.error.exceptions import ApiException

        raise ApiException(
            ErrorCode.VALIDATION_ERROR, f"{field_name} exceeds the integer range"
        )
    return number


NonBlank = BeforeValidator(lambda value: value)
"""Đánh dấu chỗ đặt kiểm tra not-blank; dùng trực tiếp trong schema với field_validator."""
