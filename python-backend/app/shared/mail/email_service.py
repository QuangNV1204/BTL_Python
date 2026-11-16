"""Gửi email xác minh / đặt lại mật khẩu, tương ứng service/EmailService.java.

Template HTML giữ nguyên nội dung của java-backend/src/main/resources/templates để
email nhận được giống hệt khi chuyển backend.
"""

from __future__ import annotations

import html
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

from app.shared.config.settings import Settings
from app.shared.error.codes import ErrorCode
from app.shared.error.exceptions import ApiException

logger = logging.getLogger("learningai.mail")

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._frontend = (settings.app_frontend_base_url or "").rstrip("/")

    def send_verification_email(self, email: str, token: str) -> None:
        link = f"{self._frontend}/verify-email?token={token}"
        body = _render(
            "verification-email.html",
            "{{verification_link}}",
            link,
        )
        plain = (
            f"Xác minh email Learning AI: {link}\n"
            "Link có hiệu lực trong 24 giờ."
        )
        self._send(
            email,
            "Learning AI - Xác minh địa chỉ email",
            plain,
            body,
            error_message=None,
        )

    def send_password_reset_email(self, email: str, token: str) -> None:
        link = f"{self._frontend}/reset-password?token={token}"
        body = _render("password-reset-email.html", "{{reset_link}}", link)
        plain = (
            f"Đặt lại mật khẩu Learning AI: {link}\n"
            "Link có hiệu lực trong 30 phút.\n"
            "Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này."
        )
        self._send(
            email,
            "Learning AI - Đặt lại mật khẩu",
            plain,
            body,
            error_message="Could not send password reset email",
        )

    def _send(
        self,
        recipient: str,
        subject: str,
        plain: str,
        html_body: str,
        error_message: str | None,
    ) -> None:
        settings = self._settings
        if not settings.mail_username or not settings.mail_password:
            # Thiếu cấu hình SMTP: báo 503 EMAIL_SEND_FAILED thay vì âm thầm bỏ qua,
            # đúng như Java khi JavaMailSender không gửi được.
            logger.error("MAIL_USERNAME/MAIL_PASSWORD chưa cấu hình; không gửi được email")
            raise ApiException(ErrorCode.EMAIL_SEND_FAILED, error_message)

        message = EmailMessage()
        message["From"] = f"Learning AI <{settings.mail_username}>"
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(plain, charset="utf-8")
        message.add_alternative(html_body, subtype="html", charset="utf-8")

        try:
            with smtplib.SMTP(settings.mail_host, settings.mail_port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(settings.mail_username, settings.mail_password)
                smtp.send_message(message)
        except Exception as exc:  # noqa: BLE001 - SMTP ném nhiều loại lỗi
            logger.error("Could not send email to %s", recipient, exc_info=exc)
            raise ApiException(ErrorCode.EMAIL_SEND_FAILED, error_message) from exc


def _render(filename: str, placeholder: str, link: str) -> str:
    try:
        template = (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Missing email template %s", filename, exc_info=exc)
        raise ApiException(ErrorCode.EMAIL_SEND_FAILED) from exc
    return template.replace(placeholder, html.escape(link))
