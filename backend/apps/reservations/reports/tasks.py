"""Celery tasks for property financial report delivery."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings

from apps.properties.models import Property
from apps.reservations.reports.delivery import (
    deliver_property_financial_report_email,
    previous_calendar_month_check_out_period,
    property_financial_report_recipients,
)
from apps.reservations.reports.types import PropertyFinancialReportParams

logger = logging.getLogger(__name__)


@shared_task(name="reservations.send_property_financial_reports_monthly")
def send_property_financial_reports_monthly() -> dict:
    if not getattr(settings, "PROPERTY_FINANCIAL_REPORT_EMAIL_ENABLED", False):
        return {"sent": False, "reason": "disabled"}

    if not (settings.EMAIL_HOST or "").strip():
        return {"sent": False, "reason": "no_smtp"}

    check_out_from, check_out_to = previous_calendar_month_check_out_period()
    sent_properties: list[dict] = []
    skipped_properties: list[dict] = []

    for prop in Property.objects.select_related("tenant").order_by("tenant_id", "slug"):
        recipients = property_financial_report_recipients(prop)
        if not recipients:
            continue

        params = PropertyFinancialReportParams(
            tenant=prop.tenant,
            property=prop,
            check_out_from=check_out_from,
            check_out_to_exclusive=check_out_to + timedelta(days=1),
        )
        try:
            params.validate()
        except Exception as exc:
            skipped_properties.append(
                {
                    "property_slug": prop.slug,
                    "tenant_slug": prop.tenant.slug,
                    "reason": str(exc),
                }
            )
            continue

        outcome = deliver_property_financial_report_email(params, recipients=recipients)
        entry = {
            "property_slug": prop.slug,
            "tenant_slug": prop.tenant.slug,
            "recipients": outcome.get("recipients", []),
            "check_out_from": check_out_from.isoformat(),
            "check_out_to": check_out_to.isoformat(),
        }
        if outcome.get("status") == "sent":
            sent_properties.append(entry)
            logger.info(
                "property financial report sent",
                extra=entry,
            )
        else:
            skipped_properties.append({**entry, "reason": outcome.get("reason", "unknown")})

    return {
        "sent": bool(sent_properties),
        "period": {
            "check_out_from": check_out_from.isoformat(),
            "check_out_to": check_out_to.isoformat(),
        },
        "sent_properties": sent_properties,
        "skipped_properties": skipped_properties,
    }
