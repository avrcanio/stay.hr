"""Email delivery for property financial reports."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from apps.reservations.reports.exports.excel import (
    property_financial_report_xlsx_filename,
    render_property_financial_report_xlsx,
)
from apps.reservations.reports.exports.pdf import (
    property_financial_report_pdf_filename,
    render_property_financial_report_pdf,
)
from apps.reservations.reports.types import PropertyFinancialReportResult

logger = logging.getLogger(__name__)

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_REPORT_FROM_NAME = "Stay.hr reports"


def property_financial_report_from_email() -> str:
    address = (settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER or "").strip()
    if not address:
        return ""
    return f"{_REPORT_FROM_NAME} <{address}>"


def format_property_financial_report_email_subject(result: PropertyFinancialReportResult) -> str:
    meta = result.meta
    return (
        f"Financijski izvještaj — {meta.property_name} "
        f"({meta.check_out_from.isoformat()} – {meta.check_out_to.isoformat()})"
    )


def format_property_financial_report_email_body(result: PropertyFinancialReportResult) -> str:
    meta = result.meta
    totals = result.totals
    lines = [
        f"Objekt: {meta.property_name}",
        f"Razdoblje odjave: {meta.check_out_from.isoformat()} – {meta.check_out_to.isoformat()}",
        f"Valuta: {meta.currency}",
        "",
        f"Rezervacija: {totals.reservation_count}",
        f"Noći: {totals.nights}",
        f"Bruto: {totals.gross} {meta.currency}",
        f"Provizija: {totals.commission} {meta.currency}",
        f"Neto: {totals.net} {meta.currency}",
    ]
    if meta.rows_with_missing_commission:
        lines.extend(
            [
                "",
                f"Upozorenje: {meta.rows_with_missing_commission} red(ova) bez provizije — "
                "neto zbroj ne uključuje te stavke.",
            ]
        )
    lines.extend(["", "U privitku su PDF i Excel verzije izvještaja.", ""])
    return "\n".join(lines)


def send_property_financial_report_email(
    result: PropertyFinancialReportResult,
    *,
    recipient: str,
) -> dict:
    if not (settings.EMAIL_HOST or "").strip():
        logger.warning("property financial report email skipped: EMAIL_HOST not configured")
        return {"status": "skipped", "reason": "no_smtp"}

    recipient = (recipient or "").strip()
    if not recipient:
        return {"status": "skipped", "reason": "no_recipient"}

    from_email = property_financial_report_from_email()
    if not from_email:
        logger.warning("property financial report email skipped: no from address")
        return {"status": "skipped", "reason": "no_from_address"}

    subject = format_property_financial_report_email_subject(result)
    body = format_property_financial_report_email_body(result)
    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[recipient],
    )
    message.attach(
        property_financial_report_pdf_filename(result),
        render_property_financial_report_pdf(result),
        "application/pdf",
    )
    message.attach(
        property_financial_report_xlsx_filename(result),
        render_property_financial_report_xlsx(result),
        _XLSX_CONTENT_TYPE,
    )
    message.send(fail_silently=False)
    return {"status": "sent", "recipient": recipient, "subject": subject}
