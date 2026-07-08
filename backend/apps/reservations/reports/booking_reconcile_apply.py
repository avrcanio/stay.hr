"""Apply selected fixes from a booking reconcile snapshot.

Transaction semantics (intentional):
- The entire ``apply_booking_reconcile_fixes()`` call runs in one ``transaction.atomic()``.
- Expected per-row outcomes (pdf_locked, nothing_to_apply, overwrite_not_confirmed, …) are
  recorded in the result tuple and do **not** abort the batch.
- An unexpected exception rolls back **all** DB changes from that apply call.
- Concurrent applies on the same reservation are serialized via ``select_for_update()``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from django.db import transaction
from django.utils import timezone

from apps.properties.models import Property
from apps.reservations.booking_xls_import import (
    BookingXlsRow,
    _merge_empty_fields,
    _operational_status_from_booking,
    upsert_reservation_from_xls_row,
)
from apps.reservations.channel_sync import IMPORT_SOURCE_BOOKING_XLS, incoming_wins, is_pdf_authoritative
from apps.reservations.models import Reservation
from apps.reservations.reports.booking_reconcile_snapshot import (
    load_booking_reconcile_snapshot,
    reservation_fingerprint,
    validate_snapshot_scope,
    xls_rows_by_external_id,
)
from apps.reservations.reports.booking_reconcile_types import (
    BookingFieldKey,
    BookingReconcileBlockReason,
)
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

ApplyMode = Literal["fill_empty", "overwrite"]


@dataclass(frozen=True)
class BookingReconcileApplyItem:
    booking_code: str
    fields: tuple[BookingFieldKey, ...] = ()
    mode: ApplyMode | None = None


@dataclass(frozen=True)
class BookingReconcileApplyRowResult:
    booking_code: str
    applied: bool
    skipped: bool
    reason: str
    reservation_id: int | None


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _field_value_from_xls(field_key: BookingFieldKey, row: BookingXlsRow):
    if field_key is BookingFieldKey.AMOUNT:
        return row.total_amount
    if field_key is BookingFieldKey.COMMISSION_AMOUNT:
        return row.commission_amount
    if field_key is BookingFieldKey.CHECK_IN:
        return row.check_in_date
    if field_key is BookingFieldKey.CHECK_OUT:
        return row.check_out_date
    if field_key is BookingFieldKey.STATUS:
        return _operational_status_from_booking(row.booking_status)
    if field_key is BookingFieldKey.UNITS_COUNT:
        return row.units_count
    raise ValueError(f"Unsupported field: {field_key}")


def _reservation_field_name(field_key: BookingFieldKey) -> str:
    mapping = {
        BookingFieldKey.AMOUNT: "amount",
        BookingFieldKey.COMMISSION_AMOUNT: "commission_amount",
        BookingFieldKey.CHECK_IN: "check_in",
        BookingFieldKey.CHECK_OUT: "check_out",
        BookingFieldKey.STATUS: "status",
        BookingFieldKey.UNITS_COUNT: "units_count",
    }
    return mapping[field_key]


def _lock_reservation(*, tenant: Tenant, booking_code: str) -> Reservation | None:
    key = (booking_code or "").strip()
    if not key:
        return None
    base = Reservation.objects.select_for_update().filter(tenant=tenant)
    found = base.filter(external_id=key).first()
    if found is not None:
        return found
    return base.filter(booking_code=key).first()


def _block_reason_for_apply(
    reservation: Reservation,
    *,
    field_key: BookingFieldKey,
    mode: ApplyMode,
) -> str:
    if is_pdf_authoritative(reservation):
        return BookingReconcileBlockReason.PDF_LOCKED
    if mode == "overwrite" and not incoming_wins(
        reservation,
        source=IMPORT_SOURCE_BOOKING_XLS,
        incoming_at=timezone.now(),
    ):
        return BookingReconcileBlockReason.STALE_XLS
    if field_key is BookingFieldKey.STATUS and reservation.status in {
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CHECKED_OUT,
    }:
        return BookingReconcileBlockReason.STATUS_PROTECTED
    if field_key is BookingFieldKey.STATUS:
        return "status_not_fixable"
    return ""


def _audit_apply_row(
    *,
    tenant_id: int,
    property_id: int,
    snapshot_id: str,
    applied_by: str,
    booking_code: str,
    reservation_id: int | None,
    mode: ApplyMode,
    fields: tuple[BookingFieldKey, ...],
    applied: bool,
    reason: str,
) -> None:
    logger.info(
        "event=booking_reconcile.apply tenant_id=%s property_id=%s snapshot_id=%s applied_by=%s "
        "booking_code=%s reservation_id=%s mode=%s fields=%s applied=%s reason=%s",
        tenant_id,
        property_id,
        snapshot_id,
        applied_by or "-",
        booking_code,
        reservation_id,
        mode,
        ",".join(str(f) for f in fields) if fields else "-",
        applied,
        reason or "-",
    )


def _apply_selected_fields(
    *,
    reservation: Reservation,
    xls_row: BookingXlsRow,
    fields: tuple[BookingFieldKey, ...],
    mode: ApplyMode,
) -> tuple[bool, str]:
    if not fields:
        return False, "no_fields"

    update_fields: dict[str, object] = {}
    for field_key in fields:
        block = _block_reason_for_apply(reservation, field_key=field_key, mode=mode)
        if block:
            return False, block
        attr = _reservation_field_name(field_key)
        value = _field_value_from_xls(field_key, xls_row)
        if mode == "fill_empty" and not _is_blank(getattr(reservation, attr)):
            continue
        update_fields[attr] = value

    if not update_fields:
        return False, "nothing_to_apply"

    if mode == "fill_empty":
        exclude = frozenset({"property"})
        if reservation.status in Reservation.OPERATIONAL_STATUSES - {
            Reservation.Status.EXPECTED,
            Reservation.Status.CANCELED,
        }:
            exclude = exclude | frozenset({"status"})
        changed = _merge_empty_fields(reservation, update_fields, exclude=exclude)
        if not changed:
            return False, "nothing_to_apply"
        reservation.save(update_fields=[*changed, "updated_at"])
        return True, ""

    for attr, value in update_fields.items():
        setattr(reservation, attr, value)
    reservation.xls_imported_at = timezone.now()
    reservation.import_source = IMPORT_SOURCE_BOOKING_XLS
    reservation.save()
    return True, ""


@transaction.atomic
def apply_booking_reconcile_fixes(
    *,
    tenant: Tenant,
    property: Property,
    snapshot_id: str,
    items: tuple[BookingReconcileApplyItem, ...],
    default_mode: ApplyMode = "fill_empty",
    confirm_overwrite: bool = False,
    applied_by: str = "",
) -> tuple[BookingReconcileApplyRowResult, ...]:
    snapshot = load_booking_reconcile_snapshot(snapshot_id)
    if snapshot is None:
        return (
            BookingReconcileApplyRowResult(
                booking_code="",
                applied=False,
                skipped=True,
                reason="snapshot_not_found",
                reservation_id=None,
            ),
        )

    scope_error = validate_snapshot_scope(
        snapshot,
        tenant_id=tenant.id,
        property_id=property.id,
    )
    if scope_error:
        return (
            BookingReconcileApplyRowResult(
                booking_code="",
                applied=False,
                skipped=True,
                reason=scope_error,
                reservation_id=None,
            ),
        )

    xls_by_code = xls_rows_by_external_id(snapshot)
    fingerprints: dict[str, str] = snapshot.get("reservation_fingerprints") or {}
    results: list[BookingReconcileApplyRowResult] = []
    applied_count = 0

    for item in items:
        booking_code = (item.booking_code or "").strip()
        mode = item.mode or default_mode
        if mode == "overwrite" and not confirm_overwrite:
            result = BookingReconcileApplyRowResult(
                booking_code=booking_code,
                applied=False,
                skipped=True,
                reason="overwrite_not_confirmed",
                reservation_id=None,
            )
            results.append(result)
            _audit_apply_row(
                tenant_id=tenant.id,
                property_id=property.id,
                snapshot_id=snapshot_id,
                applied_by=applied_by,
                booking_code=booking_code,
                reservation_id=None,
                mode=mode,
                fields=item.fields,
                applied=False,
                reason=result.reason,
            )
            continue

        xls_row = xls_by_code.get(booking_code)
        if xls_row is None:
            result = BookingReconcileApplyRowResult(
                booking_code=booking_code,
                applied=False,
                skipped=True,
                reason="row_not_in_snapshot",
                reservation_id=None,
            )
            results.append(result)
            _audit_apply_row(
                tenant_id=tenant.id,
                property_id=property.id,
                snapshot_id=snapshot_id,
                applied_by=applied_by,
                booking_code=booking_code,
                reservation_id=None,
                mode=mode,
                fields=item.fields,
                applied=False,
                reason=result.reason,
            )
            continue

        existing = _lock_reservation(tenant=tenant, booking_code=booking_code)
        if existing is None:
            import_result = upsert_reservation_from_xls_row(
                tenant=tenant,
                property=property,
                row=xls_row,
                existing_mode=mode,
            )
            if import_result.skipped:
                result = BookingReconcileApplyRowResult(
                    booking_code=booking_code,
                    applied=False,
                    skipped=True,
                    reason=import_result.skip_reason or "skipped",
                    reservation_id=import_result.reservation_id,
                )
            else:
                result = BookingReconcileApplyRowResult(
                    booking_code=booking_code,
                    applied=True,
                    skipped=False,
                    reason="imported",
                    reservation_id=import_result.reservation_id,
                )
                applied_count += 1
            results.append(result)
            _audit_apply_row(
                tenant_id=tenant.id,
                property_id=property.id,
                snapshot_id=snapshot_id,
                applied_by=applied_by,
                booking_code=booking_code,
                reservation_id=result.reservation_id,
                mode=mode,
                fields=item.fields,
                applied=result.applied,
                reason=result.reason,
            )
            continue

        expected_fp = fingerprints.get(booking_code)
        if expected_fp and reservation_fingerprint(existing) != expected_fp:
            result = BookingReconcileApplyRowResult(
                booking_code=booking_code,
                applied=False,
                skipped=True,
                reason="reservation_changed_since_compare",
                reservation_id=existing.id,
            )
            results.append(result)
            _audit_apply_row(
                tenant_id=tenant.id,
                property_id=property.id,
                snapshot_id=snapshot_id,
                applied_by=applied_by,
                booking_code=booking_code,
                reservation_id=existing.id,
                mode=mode,
                fields=item.fields,
                applied=False,
                reason=result.reason,
            )
            continue

        fields = item.fields
        if not fields:
            result = BookingReconcileApplyRowResult(
                booking_code=booking_code,
                applied=False,
                skipped=True,
                reason="no_fields",
                reservation_id=existing.id,
            )
            results.append(result)
            _audit_apply_row(
                tenant_id=tenant.id,
                property_id=property.id,
                snapshot_id=snapshot_id,
                applied_by=applied_by,
                booking_code=booking_code,
                reservation_id=existing.id,
                mode=mode,
                fields=fields,
                applied=False,
                reason=result.reason,
            )
            continue

        applied, reason = _apply_selected_fields(
            reservation=existing,
            xls_row=xls_row,
            fields=fields,
            mode=mode,
        )
        result = BookingReconcileApplyRowResult(
            booking_code=booking_code,
            applied=applied,
            skipped=not applied,
            reason=reason or ("applied" if applied else "skipped"),
            reservation_id=existing.id,
        )
        results.append(result)
        if applied:
            applied_count += 1
        _audit_apply_row(
            tenant_id=tenant.id,
            property_id=property.id,
            snapshot_id=snapshot_id,
            applied_by=applied_by,
            booking_code=booking_code,
            reservation_id=existing.id,
            mode=mode,
            fields=fields,
            applied=applied,
            reason=result.reason,
        )

    logger.info(
        "event=booking_reconcile.apply_complete tenant_id=%s property_id=%s snapshot_id=%s "
        "applied_by=%s item_count=%s applied_count=%s",
        tenant.id,
        property.id,
        snapshot_id,
        applied_by or "-",
        len(items),
        applied_count,
    )
    return tuple(results)
