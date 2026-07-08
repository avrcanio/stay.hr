"""PDF export for the property financial report."""

from __future__ import annotations

import io

from django.template.loader import render_to_string
from xhtml2pdf import pisa

from apps.billing.services.pdf import _ensure_dejavu_fonts, _link_callback
from apps.reservations.reports.exports._formatting import (
    export_filename,
    format_date_hr,
    format_datetime_hr,
    format_decimal_hr,
    display_booking_reference,
    display_external_reference,
    truncate_pdf_text,
)
from apps.reservations.reports.types import PayoutStatus, PropertyFinancialReportResult


def _payout_status_label(status: PayoutStatus) -> str:
    if status is PayoutStatus.PAID:
        return "Plaćeno"
    if status is PayoutStatus.NOT_PAID:
        return "Nije plaćeno"
    return "—"


def _template_context(result: PropertyFinancialReportResult) -> dict:
    meta = result.meta
    totals = result.totals
    return {
        "meta": {
            "property_name": meta.property_name,
            "property_slug": meta.property_slug,
            "check_out_from": format_date_hr(meta.check_out_from),
            "check_out_to": format_date_hr(meta.check_out_to),
            "generated_at": format_datetime_hr(meta.generated_at),
            "currency": meta.currency,
            "rows_with_missing_commission": meta.rows_with_missing_commission,
            "rows_without_confirmed_payout": meta.rows_without_confirmed_payout,
        },
        "rows": [
            {
                "booking_label": display_booking_reference(
                    booking_code=row.booking_code,
                    external_id=row.external_id,
                )
                or "—",
                "external_id_short": truncate_pdf_text(
                    display_external_reference(
                        booking_code=row.booking_code,
                        external_id=row.external_id,
                    )
                ),
                "check_in": format_date_hr(row.check_in),
                "check_out": format_date_hr(row.check_out),
                "room_labels": truncate_pdf_text(", ".join(row.room_labels), max_len=28),
                "nights": row.nights,
                "gross": format_decimal_hr(row.gross, null_as_zero=True),
                "commission": format_decimal_hr(row.commission),
                "net": format_decimal_hr(row.net),
                "source": truncate_pdf_text(row.source, max_len=12),
                "payout_status": _payout_status_label(row.payout_status),
                "payout_received_at": (
                    format_date_hr(row.payout_received_at)
                    if row.payout_received_at
                    else "—"
                ),
                "guest_names": [guest.name for guest in row.guests],
            }
            for row in result.rows
        ],
        "totals": {
            "reservation_count": totals.reservation_count,
            "nights": totals.nights,
            "gross": format_decimal_hr(totals.gross),
            "commission": format_decimal_hr(totals.commission),
            "net": format_decimal_hr(totals.net),
        },
        "font_regular": "DejaVuSans.ttf",
        "font_bold": "DejaVuSans-Bold.ttf",
    }


def render_property_financial_report_html(result: PropertyFinancialReportResult) -> str:
    return render_to_string(
        "reservations/reports/property_financial_report.html",
        _template_context(result),
    )


def render_property_financial_report_pdf(result: PropertyFinancialReportResult) -> bytes:
    _ensure_dejavu_fonts()
    html = render_property_financial_report_html(result)
    buffer = io.BytesIO()
    pdf = pisa.CreatePDF(
        html,
        dest=buffer,
        encoding="UTF-8",
        link_callback=_link_callback,
    )
    if pdf.err:
        raise RuntimeError("Failed to generate property financial report PDF.")
    return buffer.getvalue()


def property_financial_report_pdf_filename(result: PropertyFinancialReportResult) -> str:
    return export_filename(result, "pdf")
