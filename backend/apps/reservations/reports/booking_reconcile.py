"""Compare Booking.com XLS export against stay.hr reservations."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.reservations.booking_xls_import import BookingXlsRow
from apps.reservations.channel_sync import IMPORT_SOURCE_BOOKING_XLS, incoming_wins, is_pdf_authoritative
from apps.reservations.models import Reservation
from apps.reservations.reports.booking_reconcile_snapshot import (
    load_booking_reconcile_snapshot,
    params_from_snapshot,
    reservation_fingerprint,
    save_booking_reconcile_snapshot,
)
from apps.reservations.reports.booking_reconcile_types import (
    PARSER_VERSION,
    BookingDiffSeverity,
    BookingFieldDiff,
    BookingFieldKey,
    BookingReconcileBlockReason,
    BookingReconcileMatchKind,
    BookingReconcileMeta,
    BookingReconcileParams,
    BookingReconcileResult,
    BookingReconcileRow,
    FIELD_LABELS,
    summarize_booking_reconcile_rows,
)
from apps.reservations.reports.exports._formatting import format_date_hr, format_decimal_hr

logger = logging.getLogger(__name__)

CHANNEX_PREFIX = "channex:"
STAY_ONLY_STATUSES = (
    Reservation.Status.CHECKED_OUT,
    Reservation.Status.NO_SHOW,
)


def _display_money(value: Decimal | None) -> str:
    formatted = format_decimal_hr(value)
    if formatted == "—":
        return formatted
    return f"{formatted} €"


def _display_date(value: date | None) -> str:
    if value is None:
        return "—"
    return format_date_hr(value)


def _display_status(value: str | None) -> str:
    text = (value or "").strip()
    return text or "—"


def _normalize_decimal(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.01"))


def _decimals_equal(left: Decimal | None, right: Decimal | None) -> bool:
    return _normalize_decimal(left) == _normalize_decimal(right)


def _statuses_equivalent(*, booking_status: str, stay_status: str | None) -> bool:
    booking = (booking_status or "").strip().lower()
    stay = (stay_status or "").strip().lower()
    if booking == "ok" and stay == Reservation.Status.CHECKED_OUT:
        return True
    if booking in {"cancelled", "canceled", "cancelled_by_guest", "cancelled_by_hotel"}:
        return stay == Reservation.Status.CANCELED
    return booking == stay


def _booking_lookup_key(value: str) -> str:
    return (value or "").strip()


def _is_channex_reference(value: str) -> bool:
    return _booking_lookup_key(value).lower().startswith(CHANNEX_PREFIX)


def _reservation_booking_keys(reservation: Reservation) -> set[str]:
    keys: set[str] = set()
    for raw in (reservation.external_id, reservation.booking_code):
        key = _booking_lookup_key(raw)
        if key and not _is_channex_reference(key):
            keys.add(key)
    return keys


def _guest_display_name(reservation: Reservation | None, xls_row: BookingXlsRow | None) -> str:
    if xls_row is not None:
        if xls_row.booker_name:
            return xls_row.booker_name
        if xls_row.guest_names:
            return xls_row.guest_names[0]
    if reservation is not None:
        for guest in reservation.guests.all():
            if guest.is_primary and guest.name:
                return guest.name
        for guest in reservation.guests.all():
            if guest.name:
                return guest.name
        return reservation.booker_name or ""
    return ""


def _compute_block_reasons(
    reservation: Reservation,
    *,
    field_key: BookingFieldKey,
) -> tuple[BookingReconcileBlockReason, ...]:
    reasons: list[BookingReconcileBlockReason] = []
    if is_pdf_authoritative(reservation):
        reasons.append(BookingReconcileBlockReason.PDF_LOCKED)
    if not incoming_wins(
        reservation,
        source=IMPORT_SOURCE_BOOKING_XLS,
        incoming_at=timezone.now(),
    ):
        reasons.append(BookingReconcileBlockReason.STALE_XLS)
    if field_key is BookingFieldKey.STATUS and reservation.status in {
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CHECKED_OUT,
    }:
        reasons.append(BookingReconcileBlockReason.STATUS_PROTECTED)
    return tuple(reasons)


def _build_field_diff(
    *,
    field_key: BookingFieldKey,
    booking_value: object,
    stay_value: object,
    booking_display: str,
    stay_display: str,
    severity: BookingDiffSeverity,
    reservation: Reservation | None,
) -> BookingFieldDiff:
    fixable = field_key is not BookingFieldKey.STATUS
    block_reasons: tuple[BookingReconcileBlockReason, ...] = ()
    if reservation is not None and fixable:
        block_reasons = _compute_block_reasons(reservation, field_key=field_key)
    return BookingFieldDiff(
        field_key=field_key,
        field_label=FIELD_LABELS[field_key],
        booking_value=booking_value,  # type: ignore[arg-type]
        stay_value=stay_value,  # type: ignore[arg-type]
        booking_display=booking_display,
        stay_display=stay_display,
        severity=severity,
        fixable=fixable,
        block_reasons=block_reasons,
    )


def _compare_matched_row(
    *,
    property_id: int,
    xls_row: BookingXlsRow,
    reservation: Reservation,
) -> BookingReconcileRow:
    diffs: list[BookingFieldDiff] = []

    if not _decimals_equal(xls_row.total_amount, reservation.amount):
        diffs.append(
            _build_field_diff(
                field_key=BookingFieldKey.AMOUNT,
                booking_value=xls_row.total_amount,
                stay_value=reservation.amount,
                booking_display=_display_money(xls_row.total_amount),
                stay_display=_display_money(reservation.amount),
                severity=BookingDiffSeverity.WARNING,
                reservation=reservation,
            )
        )

    if not _decimals_equal(xls_row.commission_amount, reservation.commission_amount):
        diffs.append(
            _build_field_diff(
                field_key=BookingFieldKey.COMMISSION_AMOUNT,
                booking_value=xls_row.commission_amount,
                stay_value=reservation.commission_amount,
                booking_display=_display_money(xls_row.commission_amount),
                stay_display=_display_money(reservation.commission_amount),
                severity=BookingDiffSeverity.WARNING,
                reservation=reservation,
            )
        )

    if xls_row.check_in_date != reservation.check_in:
        diffs.append(
            _build_field_diff(
                field_key=BookingFieldKey.CHECK_IN,
                booking_value=xls_row.check_in_date,
                stay_value=reservation.check_in,
                booking_display=_display_date(xls_row.check_in_date),
                stay_display=_display_date(reservation.check_in),
                severity=BookingDiffSeverity.WARNING,
                reservation=reservation,
            )
        )

    if xls_row.check_out_date != reservation.check_out:
        diffs.append(
            _build_field_diff(
                field_key=BookingFieldKey.CHECK_OUT,
                booking_value=xls_row.check_out_date,
                stay_value=reservation.check_out,
                booking_display=_display_date(xls_row.check_out_date),
                stay_display=_display_date(reservation.check_out),
                severity=BookingDiffSeverity.WARNING,
                reservation=reservation,
            )
        )

    if xls_row.units_count is not None and xls_row.units_count != (reservation.units_count or 0):
        diffs.append(
            _build_field_diff(
                field_key=BookingFieldKey.UNITS_COUNT,
                booking_value=xls_row.units_count,
                stay_value=reservation.units_count,
                booking_display=str(xls_row.units_count),
                stay_display=str(reservation.units_count or "—"),
                severity=BookingDiffSeverity.INFO,
                reservation=reservation,
            )
        )

    if not _statuses_equivalent(
        booking_status=xls_row.booking_status,
        stay_status=reservation.status,
    ):
        diffs.append(
            _build_field_diff(
                field_key=BookingFieldKey.STATUS,
                booking_value=xls_row.booking_status,
                stay_value=reservation.status,
                booking_display=_display_status(xls_row.booking_status),
                stay_display=_display_status(reservation.status),
                severity=BookingDiffSeverity.WARNING,
                reservation=reservation,
            )
        )

    booking_code = reservation.booking_code or xls_row.external_id
    return BookingReconcileRow(
        row_key=f"{property_id}:{xls_row.external_id}",
        booking_code=booking_code,
        booking_external_id=xls_row.external_id,
        match_kind=BookingReconcileMatchKind.MATCHED,
        reservation_id=reservation.id,
        guest_name=_guest_display_name(reservation, xls_row),
        booking_status=xls_row.booking_status,
        stay_status=reservation.status,
        booking_amount=xls_row.total_amount,
        stay_amount=reservation.amount,
        booking_commission=xls_row.commission_amount,
        stay_commission=reservation.commission_amount,
        check_in=xls_row.check_in_date,
        check_out=xls_row.check_out_date,
        differences=tuple(diffs),
    )


def _missing_in_stay_row(*, property_id: int, xls_row: BookingXlsRow) -> BookingReconcileRow:
    return BookingReconcileRow(
        row_key=f"{property_id}:{xls_row.external_id}",
        booking_code=xls_row.external_id,
        booking_external_id=xls_row.external_id,
        match_kind=BookingReconcileMatchKind.MISSING_IN_STAY,
        reservation_id=None,
        guest_name=_guest_display_name(None, xls_row),
        booking_status=xls_row.booking_status,
        stay_status=None,
        booking_amount=xls_row.total_amount,
        stay_amount=None,
        booking_commission=xls_row.commission_amount,
        stay_commission=None,
        check_in=xls_row.check_in_date,
        check_out=xls_row.check_out_date,
        differences=(),
    )


def _missing_in_booking_row(*, property_id: int, reservation: Reservation) -> BookingReconcileRow:
    booking_code = reservation.booking_code or reservation.external_id or ""
    return BookingReconcileRow(
        row_key=f"{property_id}:{booking_code}",
        booking_code=booking_code,
        booking_external_id=booking_code,
        match_kind=BookingReconcileMatchKind.MISSING_IN_BOOKING,
        reservation_id=reservation.id,
        guest_name=_guest_display_name(reservation, None),
        booking_status="",
        stay_status=reservation.status,
        booking_amount=None,
        stay_amount=reservation.amount,
        booking_commission=None,
        stay_commission=reservation.commission_amount,
        check_in=reservation.check_in,
        check_out=reservation.check_out,
        differences=(),
    )


def _row_in_period(
    *,
    check_in: date,
    check_out: date,
    date_axis: str,
    date_from: date | None,
    date_to_inclusive: date | None,
) -> bool:
    if date_from is None and date_to_inclusive is None:
        return True
    axis_date = check_out if date_axis == "check_out" else check_in
    if date_from is not None and axis_date < date_from:
        return False
    if date_to_inclusive is not None and axis_date > date_to_inclusive:
        return False
    return True


def _find_reservation(
    *,
    external_id: str,
    by_external_id: dict[str, Reservation],
) -> Reservation | None:
    key = _booking_lookup_key(external_id)
    if not key:
        return None
    return by_external_id.get(key)


def _build_reservation_fingerprints(reservations: list[Reservation]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for reservation in reservations:
        fingerprint = reservation_fingerprint(reservation)
        for key in _reservation_booking_keys(reservation):
            mapping[key] = fingerprint
    return mapping


def _run_booking_reconcile_compare(
    *,
    params: BookingReconcileParams,
    filtered_rows: list[BookingXlsRow],
    parse_errors: list[tuple[int, str]] | None = None,
    content_sha256: str,
    store_snapshot: bool,
    source_snapshot_id: str | None = None,
) -> BookingReconcileResult:
    generated_at = timezone.now()
    date_axis = params.date_axis or "check_out"
    parse_errors = parse_errors or []

    reservations = list(
        Reservation.objects.filter(
            tenant=params.tenant,
            property=params.property,
        ).prefetch_related("guests")
    )
    by_key: dict[str, Reservation] = {}
    for reservation in reservations:
        for key in _reservation_booking_keys(reservation):
            by_key.setdefault(key, reservation)

    seen_xls_keys: set[str] = set()
    result_rows: list[BookingReconcileRow] = []

    for index, error in parse_errors:
        result_rows.append(
            BookingReconcileRow(
                row_key=f"{params.property.id}:parse:{index}",
                booking_code="",
                booking_external_id="",
                match_kind=BookingReconcileMatchKind.PARSE_ERROR,
                reservation_id=None,
                guest_name="",
                booking_status="",
                stay_status=None,
                booking_amount=None,
                stay_amount=None,
                booking_commission=None,
                stay_commission=None,
                check_in=None,
                check_out=None,
                differences=(),
                parse_error=error,
            )
        )

    for xls_row in filtered_rows:
        key = _booking_lookup_key(xls_row.external_id)
        seen_xls_keys.add(key)
        reservation = _find_reservation(external_id=key, by_external_id=by_key)
        if reservation is None:
            result_rows.append(
                _missing_in_stay_row(property_id=params.property.id, xls_row=xls_row)
            )
        else:
            result_rows.append(
                _compare_matched_row(
                    property_id=params.property.id,
                    xls_row=xls_row,
                    reservation=reservation,
                )
            )

    if params.date_from is not None or params.date_to_inclusive is not None:
        for reservation in reservations:
            if reservation.status not in STAY_ONLY_STATUSES:
                continue
            keys = _reservation_booking_keys(reservation)
            if not keys:
                continue
            if any(key in seen_xls_keys for key in keys):
                continue
            if not _row_in_period(
                check_in=reservation.check_in,
                check_out=reservation.check_out,
                date_axis=date_axis,
                date_from=params.date_from,
                date_to_inclusive=params.date_to_inclusive,
            ):
                continue
            result_rows.append(
                _missing_in_booking_row(
                    property_id=params.property.id,
                    reservation=reservation,
                )
            )

    rows_tuple = tuple(result_rows)
    summary = summarize_booking_reconcile_rows(rows_tuple)
    meta = BookingReconcileMeta(
        tenant_id=params.tenant.id,
        property_id=params.property.id,
        property_slug=params.property.slug,
        filename=params.filename,
        date_axis=params.date_axis,
        date_from=params.date_from,
        date_to=params.date_to_inclusive,
        generated_at=generated_at,
        parser_version=PARSER_VERSION,
    )

    snapshot_id: str | None = None
    if store_snapshot:
        snapshot_id = save_booking_reconcile_snapshot(
            params=params,
            xls_rows=filtered_rows,
            result_rows=rows_tuple,
            content_sha256=content_sha256,
            reservation_fingerprints=_build_reservation_fingerprints(reservations),
        )

    event = "booking_reconcile.recompare" if source_snapshot_id else "booking_reconcile.compare"
    logger.info(
        "event=%s tenant_id=%s property_id=%s snapshot_id=%s source_snapshot_id=%s "
        "filename=%s xls_rows=%s total_rows=%s matched=%s missing_in_stay=%s "
        "missing_in_booking=%s parse_errors=%s rows_with_differences=%s fixable_rows=%s",
        event,
        params.tenant.id,
        params.property.id,
        snapshot_id or "-",
        source_snapshot_id or "-",
        params.filename,
        len(filtered_rows),
        summary.total_rows,
        summary.matched,
        summary.missing_in_stay,
        summary.missing_in_booking,
        summary.parse_errors,
        summary.rows_with_differences,
        summary.fixable_rows,
    )

    return BookingReconcileResult(
        snapshot_id=snapshot_id,
        meta=meta,
        summary=summary,
        rows=rows_tuple,
    )


def compare_booking_export(
    *,
    params: BookingReconcileParams,
    content: bytes,
    store_snapshot: bool = True,
) -> BookingReconcileResult:
    from apps.reservations.reports.booking_reconcile_snapshot import content_sha256_hex

    parsed_rows, parse_errors = _parse_rows(content)
    filtered_rows = [
        row
        for row in parsed_rows
        if _row_in_period(
            check_in=row.check_in_date,
            check_out=row.check_out_date,
            date_axis=params.date_axis or "check_out",
            date_from=params.date_from,
            date_to_inclusive=params.date_to_inclusive,
        )
    ]
    return _run_booking_reconcile_compare(
        params=params,
        filtered_rows=filtered_rows,
        parse_errors=parse_errors,
        content_sha256=content_sha256_hex(content),
        store_snapshot=store_snapshot,
    )


def recompare_from_snapshot(
    *,
    snapshot_id: str,
    store_snapshot: bool = True,
) -> BookingReconcileResult:
    """Re-run compare using XLS rows stored in an existing snapshot (no re-upload)."""
    snapshot = load_booking_reconcile_snapshot(snapshot_id)
    if snapshot is None:
        raise ValueError("snapshot_not_found")
    params = params_from_snapshot(snapshot)
    from apps.reservations.reports.booking_reconcile_snapshot import booking_xls_row_from_dict

    xls_rows = [booking_xls_row_from_dict(raw) for raw in (snapshot.get("xls_rows") or [])]
    content_sha256 = (snapshot.get("meta") or {}).get("content_sha256") or ""
    return _run_booking_reconcile_compare(
        params=params,
        filtered_rows=xls_rows,
        content_sha256=content_sha256,
        store_snapshot=store_snapshot,
        source_snapshot_id=snapshot_id,
    )


def _parse_rows(content: bytes) -> tuple[list[BookingXlsRow], list[tuple[int, str]]]:
    import xlrd

    from apps.reservations.booking_xls_import import (
        XLS_HEADER_ALIASES,
        _cell_str,
        _map_row_dict,
        _normalize_header,
    )

    try:
        book = xlrd.open_workbook(file_contents=content)
    except Exception as exc:
        return [], [(0, str(exc))]

    sheet = book.sheet_by_index(0)
    if sheet.nrows < 2:
        return [], []

    header_map: dict[int, str] = {}
    for col in range(sheet.ncols):
        label = _normalize_header(_cell_str(sheet.cell_value(0, col)))
        field = XLS_HEADER_ALIASES.get(label)
        if field:
            header_map[col] = field

    rows: list[BookingXlsRow] = []
    errors: list[tuple[int, str]] = []
    for row_idx in range(1, sheet.nrows):
        raw: dict[str, object] = {}
        empty = True
        for col, field in header_map.items():
            value = sheet.cell_value(row_idx, col)
            if _cell_str(value):
                empty = False
            raw[field] = value
        if empty:
            continue
        try:
            rows.append(_map_row_dict(raw, book))
        except Exception as exc:
            errors.append((row_idx, str(exc)))
    return rows, errors
