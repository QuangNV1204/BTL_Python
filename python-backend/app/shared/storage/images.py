"""Nhận dạng ảnh thumbnail bằng magic bytes, tương ứng storage/ImageType.java."""

from __future__ import annotations

from enum import Enum


class ImageType(str, Enum):
    PNG = "png"
    JPEG = "jpg"
    WEBP = "webp"

    @property
    def extension(self) -> str:
        return self.value

    @property
    def media_type(self) -> str:
        return {
            ImageType.PNG: "image/png",
            ImageType.JPEG: "image/jpeg",
            ImageType.WEBP: "image/webp",
        }[self]

    @classmethod
    def detect(cls, content: bytes) -> ImageType | None:
        if (
            len(content) >= 8
            and content[0] == 0x89
            and content[1:4] == b"PNG"
            and content[4:8] == b"\r\n\x1a\n"
        ):
            return cls.PNG
        if len(content) >= 3 and content[0] == 0xFF and content[1] == 0xD8 and content[2] == 0xFF:
            return cls.JPEG
        if len(content) >= 12 and content[0:4] == b"RIFF" and content[8:12] == b"WEBP":
            return cls.WEBP
        return None


def media_type_for_key(storage_key: str) -> str | None:
    """Suy media type từ đuôi file, như FileAccessService.imageTypeOf."""
    _, _, extension = storage_key.rpartition(".")
    for image_type in ImageType:
        if image_type.extension == extension:
            return image_type.media_type
    return None
