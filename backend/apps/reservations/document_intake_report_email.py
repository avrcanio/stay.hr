"""Send ops report emails via global SMTP settings."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_ops_report_email(*, subject: str, body: str, recipient: str) -> bool:
    """Send plain-text ops report. Returns False when SMTP is not configured."""
    if not (settings.EMAIL_HOST or "").strip():
        logger.warning("ops report email skipped: EMAIL_HOST not configured")
        return False

    recipient = (recipient or "").strip()
    if not recipient:
        logger.warning("ops report email skipped: empty recipient")
        return False

    from_email = (settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER or "").strip()
    if not from_email:
        logger.warning("ops report email skipped: no from address")
        return False

    send_mail(
        subject=subject,
        message=body,
        from_email=from_email,
        recipient_list=[recipient],
        fail_silently=False,
    )
    return True
