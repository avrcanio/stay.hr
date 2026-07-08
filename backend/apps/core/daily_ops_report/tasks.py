"""Daily ops report delivery and persistence."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from apps.core.daily_ops_report.format import format_email_subject, format_markdown
from apps.core.daily_ops_report.orchestrator import run_collectors
from apps.core.daily_ops_report.snapshot import (
    load_previous_metrics,
    prune_old_files,
    save_snapshot,
    write_markdown_files,
)
from apps.core.ops_email import parse_recipients, send_ops_email

logger = logging.getLogger(__name__)


def _recipients() -> list[str]:
    raw = getattr(settings, "DAILY_OPS_REPORT_EMAILS", "")
    return parse_recipients(str(raw))


def run_daily_ops_report(
    *,
    send_email: bool = True,
    write_files: bool = True,
) -> dict:
    report = run_collectors()
    previous_metrics = load_previous_metrics()
    markdown = format_markdown(report, previous_metrics=previous_metrics)

    if write_files:
        write_markdown_files(report, markdown)
        save_snapshot(report)
        prune_old_files()

    emailed = False
    if send_email:
        recipients = _recipients()
        if not (settings.EMAIL_HOST or "").strip():
            return {
                "sent": False,
                "reason": "no_smtp",
                "overall_severity": str(report.overall_severity),
            }
        if not recipients:
            return {
                "sent": False,
                "reason": "no_recipients",
                "overall_severity": str(report.overall_severity),
            }
        subject = format_email_subject(report)
        emailed = send_ops_email(subject=subject, body=markdown, recipients=recipients)

    return {
        "sent": emailed,
        "overall_severity": str(report.overall_severity),
        "duration_ms": report.duration_ms,
        "recipients": _recipients() if send_email else [],
        "markdown": markdown,
        "report": report,
    }


@shared_task(name="core.send_daily_ops_report")
def send_daily_ops_report() -> dict:
    enabled = getattr(settings, "DAILY_OPS_REPORT_ENABLED", False)
    if not enabled:
        return {"sent": False, "reason": "disabled"}

    recipients = _recipients()
    if not recipients:
        return {"sent": False, "reason": "no_recipients"}

    if not (settings.EMAIL_HOST or "").strip():
        return {"sent": False, "reason": "no_smtp"}

    result = run_daily_ops_report(send_email=True, write_files=True)
    if result.get("sent"):
        logger.info(
            "daily ops report sent",
            extra={"recipients": recipients, "severity": result.get("overall_severity")},
        )
    return {
        "sent": bool(result.get("sent")),
        "overall_severity": result.get("overall_severity"),
        "duration_ms": result.get("duration_ms"),
        "recipients": recipients,
    }
