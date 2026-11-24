
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.shared.config.settings import Settings
from app.shared.error.exceptions import StorageException

logger = logging.getLogger("learningai.storage")

_KEY_PATTERN = re.compile(r"[A-Za-z0-9-]{1,64}\.[a-z0-9]{1,8}")


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    url: str


class LocalFileStorage:
    def __init__(self, settings: Settings) -> None:
        self._root = _canonical_root(settings.app_storage_location)
        self._public_base_url = (settings.app_storage_public_base_url or "").rstrip("/")

    def store(self, content: bytes, extension: str) -> StoredFile:
        key = f"{uuid.uuid4()}.{extension}"
        target = self._resolve(key)
        try:
            self._root.mkdir(parents=True, exist_ok=True)

            with target.open("xb") as handle:
                handle.write(content)
        except OSError as exc:
            raise StorageException("Could not write stored file") from exc
        return StoredFile(key, f"{self._public_base_url}/{key}")

    def delete(self, storage_key: str | None) -> None:
        if not storage_key or not self.is_valid_key(storage_key):
            return
        try:
            self._resolve(storage_key).unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete stored file %s", storage_key, exc_info=True)

    def exists(self, storage_key: str) -> bool:
        return self.is_valid_key(storage_key) and self._resolve(storage_key).is_file()

    def load(self, storage_key: str) -> bytes:
        if not self.is_valid_key(storage_key):
            raise StorageException("Invalid storage key")
        path = self._resolve(storage_key)
        if not path.is_file():
            raise StorageException("Stored file not found")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageException("Could not read stored file") from exc

    @staticmethod
    def is_valid_key(storage_key: str | None) -> bool:
        return bool(storage_key) and _KEY_PATTERN.fullmatch(storage_key) is not None

    def _resolve(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise StorageException("Invalid storage key")
        return path


def _canonical_root(location: Path) -> Path:
    absolute = location.expanduser().resolve()
    try:
        absolute.mkdir(parents=True, exist_ok=True)
        return absolute.resolve()
    except OSError as exc:
        raise StorageException(f"Storage directory is not usable: {absolute}") from exc
