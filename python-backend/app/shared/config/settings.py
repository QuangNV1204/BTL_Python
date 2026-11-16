"""Cấu hình ứng dụng, đọc từ biến môi trường giống java-backend/.

Giữ cùng tên biến (DBMS_*, JWT_*, AI_*, MAIL_*, APP_*) để frontend và .env chỉ cần
đổi cổng khi chuyển backend. Ngoài ra hỗ trợ DATABASE_URL của SQLAlchemy.

Thứ tự đọc: biến môi trường > ``python-backend/.env`` > ``java-backend/.env`` >
giá trị mặc định. Như vậy chạy được ngay bằng .env sẵn có của Java mà không phải
copy sang — đúng tinh thần "cùng biến môi trường" của .env.example.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _PACKAGE_ROOT.parent

# pydantic-settings: file đứng SAU ghi đè file đứng trước, nên file local của
# python-backend đặt cuối để ưu tiên cao nhất (nhưng vẫn thấp hơn biến môi trường).
_ENV_FILES = (
    _REPO_ROOT / "java-backend" / ".env",
    _PACKAGE_ROOT / ".env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
    )

    # server.port của application.yaml → SERVER_PORT; PORT để tương thích host PaaS.
    server_port: int = Field(default=8080, validation_alias=AliasChoices("SERVER_PORT", "PORT"))

    # Nguồn DB: DATABASE_URL trực tiếp, hoặc bộ ba DBMS_* của java-backend/.env.
    dbms_connection: str | None = None
    dbms_username: str | None = None
    dbms_password: str | None = None
    database_url: str | None = None

    jwt_signing_key: str = ""
    # Cùng mặc định với application.yaml (15 phút / 7 ngày).
    jwt_access_ttl_ms: int = 900_000
    jwt_refresh_ttl_ms: int = 604_800_000

    auth_cookie_secure: bool = True
    auth_cookie_same_site: str = "Lax"

    app_frontend_base_url: str = "http://localhost:5173"
    app_storage_location: Path = Path("./uploads")
    app_storage_public_base_url: str = "/api/v1/files"
    lesson_document_storage: Path = Path("./data/lesson-documents")
    # app.upload.max-thumbnail-bytes trong ThumbnailService.
    max_thumbnail_bytes: int = 5 * 1024 * 1024
    # app.storage.cleanup-delay-ms trong DocumentCleanupService.retryPending.
    cleanup_delay_ms: int = 60_000

    ai_provider: str = "mock"
    ai_base_url: str = "https://openrouter.ai/api/v1"
    ai_model: str = ""
    ai_api_key: str = ""
    ai_timeout_seconds: int = 90
    ai_max_output_tokens: int = 8192
    ai_max_source_chars: int = 20_000

    mail_host: str = "smtp.gmail.com"
    mail_port: int = 587
    mail_username: str = ""
    mail_password: str = ""

    # Nhiều origin cách nhau bằng dấu phẩy (không phải JSON như mặc định của pydantic-settings).
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        raw = (self.dbms_connection or "").strip()
        if not raw:
            raise RuntimeError(
                "Thiếu DATABASE_URL hoặc DBMS_CONNECTION; xem python-backend/.env.example"
            )
        raw = raw.removeprefix("jdbc:")
        if not raw.startswith("mysql://"):
            raise RuntimeError(f"DBMS_CONNECTION phải là jdbc:mysql://... , đang là: {raw}")
        rest = raw[len("mysql://") :]
        user = quote(self.dbms_username or "", safe="")
        password = quote(self.dbms_password or "", safe="")
        url = f"mysql+pymysql://{user}:{password}@{rest}"
        if "charset=" not in url:
            url += ("&" if "?" in url else "?") + "charset=utf8mb4"
        return url

    @property
    def signing_key_bytes(self) -> bytes:
        """jjwt dùng Base64.getDecoder().decode(signingKey); giữ đúng cách giải mã đó."""
        raw = (self.jwt_signing_key or "").strip()
        if not raw:
            raise RuntimeError("JWT_SIGNING_KEY phải được cấu hình")
        try:
            key = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError("JWT_SIGNING_KEY phải là chuỗi Base64 hợp lệ") from exc
        if len(key) < 32:
            raise RuntimeError("JWT_SIGNING_KEY phải tối thiểu 32 byte sau khi giải mã Base64")
        return key

    @property
    def ai_max_source_chars_effective(self) -> int:
        return self.ai_max_source_chars if self.ai_max_source_chars else 20_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
