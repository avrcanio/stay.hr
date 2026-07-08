from __future__ import annotations

import time
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone

from apps.billing.models import Invoice
from apps.reservations.booking_payout.events import (
    BookingPayoutLineSynced,
    emit_booking_payout_line_synced,
)
from apps.reservations.booking_payout.match import _compare_reservation_fields
from apps.reservations.booking_payout.types import (
    BookingPayoutSyncError,
    BookingPayoutSyncErrorCode,
    FieldDiff,
    SyncBatchResult,
    SyncLineResult,
    SyncPolicy,
    warning_entry,
)
from apps.reservations.booking_payout_models import (
    BookingPayoutImport,
    BookingPayoutImportStatus,
    BookingPayoutLine,
    BookingPayoutLineSyncResult,
    BookingPayoutMatchStatus,
    BookingPayoutWarningSeverity,
)
from apps.reservations.models import Reservation, ReservationVersionScope
from apps.reservations.reservation_version import touch_reservation_version

_AMOUNT_TOLERANCE = Decimal("0.01")

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    BookingPayoutImportStatus.PENDING: {
        BookingPayoutImportStatus.PARSED,
        BookingPayoutImportStatus.FAILED,
    },
    BookingPayoutImportStatus.PARSED: {
        BookingPayoutImportStatus.PARTIALLY_SYNCED,
        BookingPayoutImportStatus.APPLIED,
    },
    BookingPayoutImportStatus.PARTIALLY_SYNCED: {
        BookingPayoutImportStatus.PARTIALLY_SYNCED,
        BookingPayoutImportStatus.APPLIED,
    },
    BookingPayoutImportStatus.APPLIED: set(),
    BookingPayoutImportStatus.FAILED: set(),
}


def build_line_sync_preview(
    line: BookingPayoutLine,
    *,
    policy: SyncPolicy,
) -> list[FieldDiff]:
    import_batch = line.import_batch
    reservation = line.reservation
    if reservation is None:
        return []
    return _build_field_diffs(reservation, line, import_batch, policy=policy)


@transaction.atomic
def sync_booking_payout_line(
    line_id: int,
    *,
    applied_by,
    policy: SyncPolicy = SyncPolicy.MANUAL_OVERRIDE,
    expected_revision: int | None = None,
) -> SyncLineResult:
    line = (
        BookingPayoutLine.objects.select_for_update()
        .select_related("import_batch")
        .get(pk=line_id)
    )
    if line.reservation_id:
        Reservation.objects.select_for_update().filter(pk=line.reservation_id).first()
    return _sync_line(
        line,
        applied_by=applied_by,
        policy=policy,
        expected_revision=expected_revision,
        bump_revision=True,
    )


def sync_booking_payout_queryset(
    lines: QuerySet[BookingPayoutLine],
    *,
    applied_by,
    policy: SyncPolicy,
    expected_revision: int | None = None,
) -> SyncBatchResult:
    started = time.monotonic()
    line_ids = list(lines.order_by("line_number").values_list("pk", flat=True))
    if not line_ids:
        return SyncBatchResult([], 0, 0, 0, 0)

    import_id = (
        BookingPayoutLine.objects.filter(pk=line_ids[0])
        .values_list("import_batch_id", flat=True)
        .first()
    )

    line_results: list[SyncLineResult] = []
    with transaction.atomic():
        import_batch = (
            BookingPayoutImport.objects.select_for_update().get(pk=import_id)
        )
        if expected_revision is not None and import_batch.revision != expected_revision:
            raise BookingPayoutSyncError(
                BookingPayoutSyncErrorCode.STALE_REVISION,
                "Import se promijenio. Osvježite stranicu.",
            )

        locked_lines = list(
            BookingPayoutLine.objects.select_for_update()
            .select_related("import_batch")
            .filter(pk__in=line_ids)
            .order_by("line_number")
        )
        reservation_ids = [
            line.reservation_id for line in locked_lines if line.reservation_id
        ]
        if reservation_ids:
            list(
                Reservation.objects.select_for_update().filter(
                    pk__in=reservation_ids
                )
            )
        for line in locked_lines:
            if line.reservation_id:
                line.reservation = Reservation.objects.get(pk=line.reservation_id)
            line_results.append(
                _sync_line(
                    line,
                    applied_by=applied_by,
                    policy=policy,
                    expected_revision=None,
                    bump_revision=False,
                )
            )

        _transition_import_status(import_batch, policy=policy)
        if line_results and (
            policy == SyncPolicy.SAFE
            or (
                policy == SyncPolicy.MANUAL_OVERRIDE
                and import_batch.status == BookingPayoutImportStatus.APPLIED
            )
        ):
            now = timezone.now()
            if import_batch.applied_at is None:
                import_batch.applied_at = now
                import_batch.applied_by = applied_by
                import_batch.save(
                    update_fields=["status", "applied_at", "applied_by"]
                )
            else:
                import_batch.save(update_fields=["status"])
        else:
            import_batch.save(update_fields=["status"])

        BookingPayoutImport.objects.filter(pk=import_batch.pk).update(
            revision=F("revision") + 1
        )

    success = sum(1 for r in line_results if r.result == "SUCCESS")
    no_changes = sum(1 for r in line_results if r.result == "NO_CHANGES")
    failed = sum(1 for r in line_results if r.result == "FAILED")
    duration_ms = int((time.monotonic() - started) * 1000)
    return SyncBatchResult(
        line_results=line_results,
        success=success,
        no_changes=no_changes,
        failed=failed,
        duration_ms=duration_ms,
    )


def sync_booking_payout_import(
    import_id: int,
    *,
    applied_by,
    policy: SyncPolicy,
    line_ids: list[int] | None = None,
    expected_revision: int | None = None,
) -> SyncBatchResult:
    qs = BookingPayoutLine.objects.filter(import_batch_id=import_id)
    if line_ids is not None:
        qs = qs.filter(pk__in=line_ids)
    elif policy == SyncPolicy.MANUAL_OVERRIDE:
        qs = qs.filter(match_status=BookingPayoutMatchStatus.MATCHED)
    return sync_booking_payout_queryset(
        qs,
        applied_by=applied_by,
        policy=policy,
        expected_revision=expected_revision,
    )


def _sync_line(
    line: BookingPayoutLine,
    *,
    applied_by,
    policy: SyncPolicy,
    expected_revision: int | None,
    bump_revision: bool,
) -> SyncLineResult:
    started = time.monotonic()
    import_batch = line.import_batch

    if bump_revision and expected_revision is not None:
        if import_batch.revision != expected_revision:
            return _failed_result(
                line,
                BookingPayoutSyncErrorCode.STALE_REVISION,
                started,
            )

    perm_error = _check_permission(applied_by, policy)
    if perm_error is not None:
        return _failed_result(line, perm_error, started)

    if import_batch.status not in (
        BookingPayoutImportStatus.PARSED,
        BookingPayoutImportStatus.PARTIALLY_SYNCED,
        BookingPayoutImportStatus.APPLIED,
    ):
        return _failed_result(line, BookingPayoutSyncErrorCode.INVALID_STATUS, started)

    validation_error = _validate_sync(line, policy=policy)
    if validation_error is not None:
        if (
            validation_error == BookingPayoutSyncErrorCode.INVOICE_EXISTS
            and policy == SyncPolicy.MANUAL_OVERRIDE
            and line.applied_at
        ):
            line.last_sync_result = BookingPayoutLineSyncResult.NO_CHANGES
            line.save(update_fields=["last_sync_result"])
        else:
            line.last_sync_result = BookingPayoutLineSyncResult.FAILED
            line.save(update_fields=["last_sync_result"])
        return _failed_result(line, validation_error, started)

    reservation = line.reservation
    if reservation is None and line.reservation_id:
        reservation = Reservation.objects.get(pk=line.reservation_id)
        line.reservation = reservation
    if reservation is None:
        return _failed_result(
            line,
            BookingPayoutSyncErrorCode.RESERVATION_MISSING,
            started,
        )

    field_diffs = _build_field_diffs(reservation, line, import_batch, policy=policy)
    changed_diffs = [d for d in field_diffs if d.changed]
    has_changes = len(changed_diffs) > 0

    if not has_changes:
        now = timezone.now()
        if policy == SyncPolicy.SAFE:
            line.applied_at = line.applied_at or now
            line.last_sync_result = BookingPayoutLineSyncResult.NO_CHANGES
            line.save(update_fields=["applied_at", "last_sync_result"])
        else:
            line.reservation_synced_at = line.reservation_synced_at or now
            line.reservation_synced_by = applied_by
            line.last_sync_result = BookingPayoutLineSyncResult.NO_CHANGES
            line.save(
                update_fields=[
                    "reservation_synced_at",
                    "reservation_synced_by",
                    "last_sync_result",
                ]
            )
        _transition_import_status(import_batch, policy=policy)
        if bump_revision:
            _bump_revision(import_batch)
            import_batch.save(update_fields=["status"])
        duration_ms = int((time.monotonic() - started) * 1000)
        return SyncLineResult(
            line_id=line.pk,
            result="NO_CHANGES",
            error_code=None,
            field_diffs=field_diffs,
            updated_fields_count=0,
            duration_ms=duration_ms,
        )

    reservation_before = _snapshot_reservation(reservation)
    _write_reservation(
        reservation,
        line,
        import_batch,
        policy=policy,
        applied_by=applied_by,
    )
    reservation_after = _snapshot_reservation(reservation)

    now = timezone.now()
    sync_reason = ""
    if policy == SyncPolicy.MANUAL_OVERRIDE and _had_pdf_source(reservation_before):
        sync_reason = "booking_payout_override_pdf"

    line.reservation_before_sync = reservation_before
    line.reservation_after_sync = reservation_after
    line.reservation_sync_reason = sync_reason
    line.warnings = _regenerate_line_warnings(line)
    line.last_sync_result = BookingPayoutLineSyncResult.SUCCESS

    if policy == SyncPolicy.SAFE:
        line.applied_at = now
        line.save(
            update_fields=[
                "applied_at",
                "reservation_before_sync",
                "reservation_after_sync",
                "reservation_sync_reason",
                "warnings",
                "last_sync_result",
            ]
        )
    else:
        line.reservation_synced_at = now
        line.reservation_synced_by = applied_by
        line.save(
            update_fields=[
                "reservation_synced_at",
                "reservation_synced_by",
                "reservation_before_sync",
                "reservation_after_sync",
                "reservation_sync_reason",
                "warnings",
                "last_sync_result",
            ]
        )

    _transition_import_status(import_batch, policy=policy)
    if bump_revision:
        _bump_revision(import_batch)
        import_batch.save(update_fields=["status"])

    touch_reservation_version(
        reservation.pk,
        ReservationVersionScope.PAYMENTS,
        reason="booking_payout_sync",
    )

    emit_booking_payout_line_synced(
        BookingPayoutLineSynced(
            line_id=line.pk,
            reservation_id=reservation.pk,
            import_id=import_batch.pk,
            policy=policy,
            result="SUCCESS",
            applied_by_id=getattr(applied_by, "pk", None),
            field_diffs=tuple(changed_diffs),
        )
    )

    duration_ms = int((time.monotonic() - started) * 1000)
    return SyncLineResult(
        line_id=line.pk,
        result="SUCCESS",
        error_code=None,
        field_diffs=field_diffs,
        updated_fields_count=len(changed_diffs),
        duration_ms=duration_ms,
    )


def _failed_result(
    line: BookingPayoutLine,
    error_code: BookingPayoutSyncErrorCode,
    started: float,
) -> SyncLineResult:
    duration_ms = int((time.monotonic() - started) * 1000)
    return SyncLineResult(
        line_id=line.pk,
        result="FAILED",
        error_code=error_code,
        field_diffs=[],
        updated_fields_count=0,
        duration_ms=duration_ms,
    )


def _check_permission(applied_by, policy: SyncPolicy) -> BookingPayoutSyncErrorCode | None:
    if policy == SyncPolicy.FORCE:
        if applied_by is None or not getattr(applied_by, "is_superuser", False):
            return BookingPayoutSyncErrorCode.PERMISSION_DENIED
        return None
    if policy == SyncPolicy.MANUAL_OVERRIDE:
        if applied_by is None:
            return BookingPayoutSyncErrorCode.PERMISSION_DENIED
        if not applied_by.has_perm("reservations.apply_booking_payout_line"):
            return BookingPayoutSyncErrorCode.PERMISSION_DENIED
    return None


def _validate_sync(
    line: BookingPayoutLine,
    *,
    policy: SyncPolicy,
) -> BookingPayoutSyncErrorCode | None:
    if line.match_status == BookingPayoutMatchStatus.UNMATCHED:
        return BookingPayoutSyncErrorCode.UNMATCHED
    if line.match_status == BookingPayoutMatchStatus.DUPLICATE:
        return BookingPayoutSyncErrorCode.DUPLICATE
    if line.reservation_id is None:
        return BookingPayoutSyncErrorCode.RESERVATION_MISSING

    reservation = line.reservation
    import_batch = line.import_batch

    if policy == SyncPolicy.MANUAL_OVERRIDE:
        if Invoice.objects.filter(reservation_id=reservation.pk).exists():
            return BookingPayoutSyncErrorCode.INVOICE_EXISTS

    if (
        reservation.booking_payout_id
        and reservation.booking_payout_id != import_batch.payout_id
        and reservation.booking_payout_line_id != line.pk
    ):
        return BookingPayoutSyncErrorCode.PAYOUT_ID_CONFLICT

    if policy == SyncPolicy.SAFE:
        if reservation.booking_payout_line_id == line.pk:
            return None
        if reservation.booking_payout_id == import_batch.payout_id:
            return None

    return None


def _build_field_diffs(
    reservation: Reservation,
    line: BookingPayoutLine,
    import_batch: BookingPayoutImport,
    *,
    policy: SyncPolicy,
) -> list[FieldDiff]:
    targets = _target_field_values(reservation, line, import_batch, policy=policy)
    diffs: list[FieldDiff] = []
    for field_name, new_value in targets.items():
        old_raw = getattr(reservation, field_name, None)
        old_str = _field_to_str(field_name, old_raw)
        new_str = _field_to_str(field_name, new_value)
        changed = old_str != new_str
        diffs.append(
            FieldDiff(field=field_name, old=old_str, new=new_str, changed=changed)
        )
    return diffs


def _target_field_values(
    reservation: Reservation,
    line: BookingPayoutLine,
    import_batch: BookingPayoutImport,
    *,
    policy: SyncPolicy,
) -> dict[str, object]:
    values: dict[str, object] = {}
    if policy == SyncPolicy.MANUAL_OVERRIDE:
        values["amount"] = line.gross_amount
        values["commission_amount"] = line.commission_amount
        values["currency"] = line.currency
    if policy in (SyncPolicy.SAFE, SyncPolicy.MANUAL_OVERRIDE):
        values["booking_payout_received_at"] = import_batch.payout_date
        values["booking_payout_id"] = import_batch.payout_id
        values["booking_payout_net"] = line.net_amount
        values["booking_payout_service_fee"] = line.service_fee
    if policy == SyncPolicy.FORCE:
        values.update(
            _target_field_values(
                reservation, line, import_batch, policy=SyncPolicy.MANUAL_OVERRIDE
            )
        )
    return values


def _write_reservation(
    reservation: Reservation,
    line: BookingPayoutLine,
    import_batch: BookingPayoutImport,
    *,
    policy: SyncPolicy,
    applied_by,
) -> None:
    update_fields: list[str] = []
    targets = _target_field_values(reservation, line, import_batch, policy=policy)

    for field_name, new_value in targets.items():
        if getattr(reservation, field_name) != new_value:
            setattr(reservation, field_name, new_value)
            update_fields.append(field_name)

    reservation.booking_payout_line = line
    update_fields.append("booking_payout_line")

    if policy in (SyncPolicy.MANUAL_OVERRIDE, SyncPolicy.FORCE):
        reservation.financial_source = Reservation.FinancialSource.BOOKING_PAYOUT
        reservation.financial_synced_at = timezone.now()
        reservation.financial_synced_by = applied_by
        update_fields.extend(
            ["financial_source", "financial_synced_at", "financial_synced_by"]
        )

    update_fields.append("updated_at")
    reservation.save(update_fields=list(dict.fromkeys(update_fields)))


def _regenerate_line_warnings(line: BookingPayoutLine) -> dict[str, dict]:
    reservation = line.reservation
    if reservation is None:
        return {}

    warnings: dict[str, dict] = {}
    row_like = _LineRowAdapter(line)
    _compare_reservation_fields(row_like, reservation, warnings)

    if line.service_fee > 0:
        warnings.setdefault(
            "service_fee",
            warning_entry(
                BookingPayoutWarningSeverity.INFO,
                csv=line.service_fee,
                message="Payments service fee present",
            ),
        )

    import_batch = line.import_batch
    if (
        reservation.booking_payout_id
        and reservation.booking_payout_id != import_batch.payout_id
    ):
        warnings["existing_payout"] = warning_entry(
            BookingPayoutWarningSeverity.WARNING,
            message="Reservation already has a different payout",
            reservation=reservation.booking_payout_id,
            csv=import_batch.payout_id,
        )

    return warnings


class _LineRowAdapter:
    """Minimal row interface for match._compare_reservation_fields."""

    def __init__(self, line: BookingPayoutLine) -> None:
        self.gross_amount = line.gross_amount
        self.commission_amount = line.commission_amount
        self.check_in = line.check_in
        self.check_out = line.check_out
        self.net_amount = line.net_amount


def _snapshot_reservation(reservation: Reservation) -> dict[str, str | None]:
    return {
        "amount": _decimal_str(reservation.amount),
        "commission_amount": _decimal_str(reservation.commission_amount),
        "currency": reservation.currency or "",
        "booking_payout_id": reservation.booking_payout_id or "",
        "booking_payout_net": _decimal_str(reservation.booking_payout_net),
    }


def _had_pdf_source(snapshot: dict[str, str | None]) -> bool:
    return bool(snapshot.get("amount") or snapshot.get("commission_amount"))


def _decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _field_to_str(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _transition_import_status(
    import_batch: BookingPayoutImport,
    *,
    policy: SyncPolicy,
) -> None:
    matched = import_batch.matched_lines_count
    if matched == 0:
        return

    if policy == SyncPolicy.SAFE:
        applied = import_batch.lines.filter(
            match_status=BookingPayoutMatchStatus.MATCHED,
            applied_at__isnull=False,
        ).count()
        if applied != matched:
            return
        new_status = BookingPayoutImportStatus.APPLIED
    else:
        synced = import_batch.synced_lines_count
        if synced == 0:
            return
        if synced == matched:
            new_status = BookingPayoutImportStatus.APPLIED
        else:
            new_status = BookingPayoutImportStatus.PARTIALLY_SYNCED

    current = import_batch.status
    if new_status == current:
        return

    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise BookingPayoutSyncError(
            BookingPayoutSyncErrorCode.INVALID_TRANSITION,
            f"Cannot transition from {current} to {new_status}",
        )

    import_batch.status = new_status


def _bump_revision(import_batch: BookingPayoutImport) -> None:
    BookingPayoutImport.objects.filter(pk=import_batch.pk).update(
        revision=F("revision") + 1
    )
    import_batch.refresh_from_db(fields=["revision"])
