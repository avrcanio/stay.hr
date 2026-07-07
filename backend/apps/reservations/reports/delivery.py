"""Build and deliver property financial reports by email."""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone
from zoneinfo import ZoneInfo

from apps.properties.models import Property
from apps.reservations.reports.email import send_property_financial_report_email
from apps.reservations.reports.property_financial_report import build_property_financial_report
from apps.reservations.reports.recipients import parse_financial_report_recipients
from apps.reservations.reports.types import PropertyFinancialReportParams

ZAGREB = ZoneInfo("Europe/Zagreb")


def previous_calendar_month_check_out_period(
    *,
    today: date | None = None,
) -> tuple[date, date]:
    reference = today or timezone.now().astimezone(ZAGREB).date()
    first_this_month = reference.replace(day=1)
    last_previous = first_this_month - timedelta(days=1)
    first_previous = last_previous.replace(day=1)
    return first_previous, last_previous


def property_financial_report_recipients(prop: Property) -> list[str]:
    return parse_financial_report_recipients(prop.financial_report_recipients)


def deliver_property_financial_report_email(
    params: PropertyFinancialReportParams,
    *,
    recipients: list[str],
) -> dict:
    normalized = parse_financial_report_recipients(",".join(recipients))
    if not normalized:
        return {"status": "skipped", "reason": "no_recipient"}

    result = build_property_financial_report(params)
    sent: list[str] = []
    for recipient in normalized:
        outcome = send_property_financial_report_email(result, recipient=recipient)
        if outcome.get("status") == "sent":
            sent.append(recipient)

    if not sent:
        return {"status": "skipped", "reason": "send_failed", "recipients": normalized}

    return {
        "status": "sent",
        "recipients": sent,
        "subject": outcome.get("subject"),
        "reservation_count": result.totals.reservation_count,
    }
