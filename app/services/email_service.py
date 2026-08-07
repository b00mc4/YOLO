from __future__ import annotations
import logging
import smtplib
from email.message import EmailMessage
from time import monotonic
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class _EmailServiceHealth:
    _DEGRADED_COOLDOWN_SECONDS = 60.0
    __slots__ = ("_degraded_until",)

    def __init__(self) -> None:
        self._degraded_until = 0.0

    def is_degraded(self) -> bool:
        return monotonic() < self._degraded_until

    def mark_failure(self) -> None:
        self._degraded_until = monotonic() + self._DEGRADED_COOLDOWN_SECONDS

    def mark_recovered(self) -> None:
        self._degraded_until = 0.0


_email_health = _EmailServiceHealth()


def is_email_service_degraded() -> bool:
    return _email_health.is_degraded()

def _send_email(to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    except Exception:
        _email_health.mark_failure()
        raise
    else:
        _email_health.mark_recovered()

def send_set_password_email(to_email: str, raw_token: str) -> None:
    link = f"{settings.frontend_url}/set-password?token={raw_token}"
    _send_email(
        to_email=to_email,
        subject="ตั้งรหัสผ่านบัญชีของคุณ",
        body=f"กรุณาคลิกลิงก์เพื่อตั้งรหัสผ่าน: {link}",
    )


def send_invite_email(to_email: str, raw_token: str) -> None:
    link = f"{settings.frontend_url}/set-password?token={raw_token}"
    _send_email(
        to_email=to_email,
        subject="ยินดีต้อนรับเข้าสู่ระบบ Village Guard",
        body=f"คุณได้รับเชิญให้เข้าใช้งานระบบ กรุณาคลิกลิงก์เพื่อตั้งรหัสผ่านและเริ่มใช้งานบัญชีของคุณ: {link}",
    )

def send_set_password_email_background(to_email: str, raw_token: str) -> None:
    try:
        send_set_password_email(to_email, raw_token)
    except Exception:
        logger.warning("Failed to send password reset email to %s", to_email)