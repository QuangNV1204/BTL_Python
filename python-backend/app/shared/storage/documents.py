"""Lưu và trích text tài liệu bài học.

Java dùng Apache Tika; Python dùng pypdf cho PDF và python-docx cho DOCX, txt đọc
trực tiếp. Phạm vi MIME giữ đúng ALLOWED_MEDIA_TYPES của LessonService.
"""

from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path, PurePath

from app.shared.config.settings import Settings
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException

logger = logging.getLogger("learningai.documents")

PDF_TYPE = "application/pdf"
TEXT_TYPE = "text/plain"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_MEDIA_TYPES = frozenset({PDF_TYPE, TEXT_TYPE, DOCX_TYPE})


class DocumentStorage:
    """Tương ứng service/LocalDocumentStorage.java."""

    def __init__(self, settings: Settings) -> None:
        self._root = settings.lesson_document_storage.expanduser().resolve()

    @staticmethod
    def new_key(original_name: str | None) -> str:
        name = PurePath((original_name or "document").replace("\\", "/")).name
        suffix = Path(name).suffix if "." in name else ""
        return f"{uuid.uuid4()}{suffix.lower()}"

    def store(self, storage_key: str, content: bytes) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self._resolve(storage_key).write_bytes(content)
        except OSError as exc:
            raise ApiException(ErrorCode.STORAGE_ERROR) from exc

    def load(self, storage_key: str) -> bytes:
        path = self._resolve(storage_key)
        if not path.is_file():
            raise ApiException(ErrorCode.NOT_FOUND, "Document content not found")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise ApiException(ErrorCode.STORAGE_ERROR) from exc

    def delete(self, storage_key: str) -> None:
        try:
            self._resolve(storage_key).unlink(missing_ok=True)
        except OSError as exc:
            raise ApiException(ErrorCode.STORAGE_ERROR) from exc

    def exists(self, storage_key: str) -> bool:
        return self._resolve(storage_key).is_file()

    def _resolve(self, storage_key: str) -> Path:
        path = (self._root / storage_key).resolve()
        if not path.is_relative_to(self._root):
            raise ApiException(ErrorCode.STORAGE_ERROR)
        return path


def extract_text(content: bytes, media_type: str) -> str | None:
    """Trích text; rỗng trả None. Lỗi parser → 415 như TikaDocumentTextExtractor."""
    try:
        if media_type == TEXT_TYPE:
            text = content.decode("utf-8", errors="replace")
        elif media_type == PDF_TYPE:
            text = _extract_pdf(content)
        elif media_type == DOCX_TYPE:
            text = _extract_docx(content)
        else:
            raise ApiException(ErrorCode.UNSUPPORTED_FILE_TYPE)
    except ApiException:
        raise
    except Exception as exc:  # noqa: BLE001 - parser bên thứ ba ném nhiều loại lỗi
        logger.warning("Could not extract text from %s", media_type, exc_info=exc)
        raise ApiException(
            ErrorCode.UNSUPPORTED_FILE_TYPE, "Could not extract text from document"
        ) from exc
    stripped = (text or "").strip()
    return stripped or None


def _extract_pdf(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(content: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)
