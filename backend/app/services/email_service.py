"""Small SMTP adapter for transactional Saaya email.

Delivery is intentionally optional: without SMTP configuration the caller can
still complete its database transaction and retry delivery after configuration.
No message body or authentication token is written to logs.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


log = logging.getLogger(__name__)


def configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_from_email)


async def send_email(*, to: str, subject: str, text: str) -> bool:
    s = get_settings()
    if not configured():
        log.info("email delivery skipped: SMTP is not configured (recipient domain=%s)", to.rsplit("@", 1)[-1])
        return False

    message = EmailMessage()
    message["From"] = s.smtp_from_email
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)

    def _send() -> None:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(message)

    try:
        await asyncio.to_thread(_send)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("email delivery failed (%s)", type(exc).__name__)
        return False


async def send_verification(*, to: str, token: str) -> bool:
    s = get_settings()
    url = f"{s.frontend_url.rstrip('/')}/verify-email?token={token}"
    return await send_email(
        to=to,
        subject="Verify your Saaya email",
        text=(
            "Welcome to Saaya. Verify your email using the link below.\n\n"
            f"{url}\n\nThis link expires in 24 hours. If you did not create this account, ignore this email."
        ),
    )


async def send_password_reset(*, to: str, token: str) -> bool:
    s = get_settings()
    url = f"{s.frontend_url.rstrip('/')}/reset-password?token={token}"
    return await send_email(
        to=to,
        subject="Reset your Saaya password",
        text=(
            "A password reset was requested for your Saaya account.\n\n"
            f"{url}\n\nThis link expires in 30 minutes. If this was not you, no action is needed."
        ),
    )


__all__ = ["configured", "send_email", "send_verification", "send_password_reset"]
