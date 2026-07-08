"""Serializers for reception report endpoints."""

from __future__ import annotations

from decimal import Decimal

from apps.reservations.reports.types import (
    PropertyFinancialReportGuestRow,
    PropertyFinancialReportResult,
    PropertyFinancialReportRow,
)
from apps.reservations.statistics import _decimal_str as _statistics_decimal_str


def _decimal_str(value, *, null_as_zero: bool = False) -> str | None:
    if value is None:
        if null_as_zero:
            return _statistics_decimal_str(Decimal("0"))
        return None
    return _statistics_decimal_str(value)


def _guest_row_payload(row: PropertyFinancialReportGuestRow) -> dict:
    return {
        "name": row.name,
        "nationality_iso2": row.nationality_iso2,
        "is_primary": row.is_primary,
    }


def _report_row_payload(row: PropertyFinancialReportRow) -> dict:
    return {
        "reservation_id": row.reservation_id,
        "booking_code": row.booking_code,
        "external_id": row.external_id,
        "check_in": row.check_in.isoformat(),
        "check_out": row.check_out.isoformat(),
        "status": row.status,
        "room_labels": list(row.room_labels),
        "nights": row.nights,
        "gross": _decimal_str(row.gross, null_as_zero=True),
        "commission": _decimal_str(row.commission),
        "net": _decimal_str(row.net),
        "currency": row.currency,
        "source": row.source,
        "guests": [_guest_row_payload(guest) for guest in row.guests],
        "payout_status": row.payout_status.value,
        "payout_received_at": (
            row.payout_received_at.isoformat() if row.payout_received_at else None
        ),
        "paid_amount": _decimal_str(row.paid_amount),
    }


def property_financial_report_to_dict(result: PropertyFinancialReportResult) -> dict:
    meta = result.meta
    totals = result.totals
    return {
        "meta": {
            "property_name": meta.property_name,
            "property_slug": meta.property_slug,
            "check_out_from": meta.check_out_from.isoformat(),
            "check_out_to": meta.check_out_to.isoformat(),
            "generated_at": meta.generated_at.isoformat(),
            "currency": meta.currency,
            "max_period_days": meta.max_period_days,
            "rows_with_missing_commission": meta.rows_with_missing_commission,
            "rows_without_confirmed_payout": meta.rows_without_confirmed_payout,
        },
        "rows": [_report_row_payload(row) for row in result.rows],
        "totals": {
            "reservation_count": totals.reservation_count,
            "nights": totals.nights,
            "gross": _decimal_str(totals.gross),
            "commission": _decimal_str(totals.commission),
            "net": _decimal_str(totals.net),
        },
    }
