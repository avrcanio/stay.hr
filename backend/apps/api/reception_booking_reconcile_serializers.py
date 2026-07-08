"""Serializers for booking reconcile reception API.

JSON responses are additive-only: new optional fields may appear without breaking clients.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from apps.reservations.reports.booking_reconcile_apply import BookingReconcileApplyRowResult
from apps.reservations.reports.booking_reconcile_types import (
    BookingFieldDiff,
    BookingFieldKey,
    BookingReconcileResult,
    BookingReconcileRow,
    BookingReconcileSummary,
    BookingReconcileValue,
)
from apps.reservations.statistics import _decimal_str


def _serialize_value(value: BookingReconcileValue) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return _decimal_str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, int):
        return value
    return str(value)


def _field_diff_payload(diff: BookingFieldDiff) -> dict:
    return {
        "field_key": str(diff.field_key),
        "field_label": diff.field_label,
        "booking_value": _serialize_value(diff.booking_value),
        "stay_value": _serialize_value(diff.stay_value),
        "booking_display": diff.booking_display,
        "stay_display": diff.stay_display,
        "severity": str(diff.severity),
        "fixable": diff.fixable,
        "block_reasons": [str(reason) for reason in diff.block_reasons],
    }


def _row_payload(row: BookingReconcileRow) -> dict:
    return {
        "row_key": row.row_key,
        "booking_code": row.booking_code,
        "booking_external_id": row.booking_external_id,
        "match_kind": str(row.match_kind),
        "reservation_id": row.reservation_id,
        "guest_name": row.guest_name,
        "booking_status": row.booking_status,
        "stay_status": row.stay_status,
        "booking_amount": _serialize_value(row.booking_amount),
        "stay_amount": _serialize_value(row.stay_amount),
        "booking_commission": _serialize_value(row.booking_commission),
        "stay_commission": _serialize_value(row.stay_commission),
        "check_in": _serialize_value(row.check_in),
        "check_out": _serialize_value(row.check_out),
        "differences": [_field_diff_payload(diff) for diff in row.differences],
        "parse_error": row.parse_error,
        "has_differences": row.has_differences,
        "is_fixable": row.is_fixable,
    }


def _summary_payload(summary: BookingReconcileSummary) -> dict:
    return {
        "total_rows": summary.total_rows,
        "matched": summary.matched,
        "missing_in_stay": summary.missing_in_stay,
        "missing_in_booking": summary.missing_in_booking,
        "parse_errors": summary.parse_errors,
        "rows_with_differences": summary.rows_with_differences,
        "fixable_rows": summary.fixable_rows,
        "booking_total_amount": _decimal_str(summary.booking_total_amount),
        "stay_total_amount": _decimal_str(summary.stay_total_amount),
        "booking_total_commission": _decimal_str(summary.booking_total_commission),
        "stay_total_commission": _decimal_str(summary.stay_total_commission),
    }


def booking_reconcile_result_to_dict(result: BookingReconcileResult) -> dict:
    meta = result.meta
    return {
        "snapshot_id": result.snapshot_id,
        "meta": {
            "tenant_id": meta.tenant_id,
            "property_id": meta.property_id,
            "property_slug": meta.property_slug,
            "filename": meta.filename,
            "date_axis": meta.date_axis,
            "date_from": _serialize_value(meta.date_from),
            "date_to": _serialize_value(meta.date_to),
            "generated_at": meta.generated_at.isoformat(),
            "parser_version": meta.parser_version,
        },
        "summary": _summary_payload(result.summary),
        "rows": [_row_payload(row) for row in result.rows],
    }


def booking_reconcile_apply_results_to_dict(
    results: tuple[BookingReconcileApplyRowResult, ...],
) -> dict:
    return {
        "results": [
            {
                "booking_code": row.booking_code,
                "applied": row.applied,
                "skipped": row.skipped,
                "reason": row.reason,
                "reservation_id": row.reservation_id,
            }
            for row in results
        ]
    }


def parse_apply_field_keys(raw_fields: list[str]) -> tuple[BookingFieldKey, ...]:
    keys: list[BookingFieldKey] = []
    for raw in raw_fields:
        try:
            keys.append(BookingFieldKey(raw))
        except ValueError as exc:
            raise ValueError(f"Unknown field: {raw}") from exc
    return tuple(keys)
