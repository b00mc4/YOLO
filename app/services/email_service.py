from __future__ import annotations
import smtplib
from email.message import EmailMessage
from app.core.config import get_settings

settings = get_settings()

def _send_email(to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


def send_set_password_email(to_email: str, raw_token: str) -> None:
    link = f"{settings.frontend_url}/set-password?token={raw_token}"
    _send_email(
        to_email=to_email,
        subject="ตั้งรหัสผ่านบัญชีของคุณ",
        body=f"กรุณาคลิกลิงก์เพื่อตั้งรหัสผ่าน: {link}",
    )