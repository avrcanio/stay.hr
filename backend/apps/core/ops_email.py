"""Plain-text ops email helper (multi-recipient)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_ops_email(*, subject: str, body: str, recipients: list[str]) -> bool:
    """Send plain-text ops report to one or more recipients."""
    if not (settings.EMAIL_HOST or "").strip():
        logger.warning("ops email skipped: EMAIL_HOST not configured")
        return False

    cleaned = [item.strip() for item in recipients if (item or "").strip()]
    if not cleaned:
        logger.warning("ops email skipped: empty recipients")
        return False

    from_email = (settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER or "").strip()
    if not from_email:
        logger.warning("ops email skipped: no from address")
        return False

    send_mail(
        subject=subject,
        message=body,
        from_email=from_email,
        recipient_list=cleaned,
        fail_silently=False,
    )
    return True


def parse_recipients(raw: str) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]
