"""Celery tasks for document intake telemetry reporting."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from zoneinfo import ZoneInfo

from apps.reservations.document_intake_report_email import send_ops_report_email
from apps.reservations.document_intake_report_snapshot import (
    load_report_snapshot,
    save_report_snapshot,
    should_send_report_today,
)
from apps.reservations.document_intake_telemetry import (
    QUALITY_MODEL_ID,
    format_report_email_subject,
    format_telemetry_report,
    load_document_intake_quality_kpis,
)

logger = logging.getLogger(__name__)
ZAGREB = ZoneInfo("Europe/Zagreb")


@shared_task(name="reservations.send_document_intake_quality_report")
def send_document_intake_quality_report() -> dict:
    enabled = getattr(settings, "DOCUMENT_INTAKE_QUALITY_REPORT_ENABLED", False)
    recipient = (getattr(settings, "DOCUMENT_INTAKE_QUALITY_REPORT_EMAIL", None) or "").strip()
    days = max(1, int(getattr(settings, "DOCUMENT_INTAKE_QUALITY_REPORT_DAYS", 7)))
    send_every_days = max(
        1, int(getattr(settings, "DOCUMENT_INTAKE_QUALITY_REPORT_SEND_EVERY_DAYS", 1))
    )
    monday_only = bool(getattr(settings, "DOCUMENT_INTAKE_QUALITY_REPORT_MONDAY_ONLY", False))

    if not enabled:
        return {"sent": False, "reason": "disabled"}

    if not recipient:
        return {"sent": False, "reason": "no_recipient"}

    if not (settings.EMAIL_HOST or "").strip():
        return {"sent": False, "reason": "no_smtp"}

    snapshot = load_report_snapshot()
    should_send, skip_reason = should_send_report_today(
        snapshot=snapshot,
        send_every_days=send_every_days,
        monday_only=monday_only,
    )
    if not should_send:
        return {
            "sent": False,
            "reason": skip_reason,
            "days": days,
            "send_every_days": send_every_days,
        }

    kpis = load_document_intake_quality_kpis(
        days=days,
        quality_model=QUALITY_MODEL_ID,
    )
    report_date = timezone.now().astimezone(ZAGREB).date()
    body = format_telemetry_report(
        kpis,
        previous_snapshot=snapshot,
        for_email=True,
    )
    subject = format_report_email_subject(days=days, report_date=report_date)

    if not send_ops_report_email(subject=subject, body=body, recipient=recipient):
        return {"sent": False, "reason": "send_failed", "days": days, "recipient": recipient}

    save_report_snapshot(
        kpis=kpis,
        lookback_days=days,
        send_every_days=send_every_days,
    )
    logger.info(
        "document intake quality report sent",
        extra={"recipient": recipient, "days": days},
    )
    return {
        "sent": True,
        "days": days,
        "recipient": recipient,
        "send_every_days": send_every_days,
        "lookback_days": days,
    }
