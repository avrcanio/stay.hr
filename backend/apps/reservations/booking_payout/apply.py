from __future__ import annotations

from apps.reservations.booking_payout.sync import sync_booking_payout_import
from apps.reservations.booking_payout.types import LineApplyResult, PayoutImportResult, SyncPolicy
from apps.reservations.booking_payout_models import (
    BookingPayoutImport,
    BookingPayoutLine,
    BookingPayoutMatchStatus,
)


def apply_booking_payout_import(import_id: int, *, applied_by=None) -> PayoutImportResult:
    """Legacy bulk Apply payout — payout fields only (SyncPolicy.SAFE)."""
    batch_result = sync_booking_payout_import(
        import_id,
        applied_by=applied_by,
        policy=SyncPolicy.SAFE,
    )

    results_by_line = {r.line_id: r for r in batch_result.line_results}
    lines = BookingPayoutLine.objects.filter(import_batch_id=import_id).order_by(
        "line_number"
    )

    line_results: list[LineApplyResult] = []
    matched = unmatched = duplicates = applied = skipped = warnings = errors = 0

    for line in lines:
        if line.match_status == BookingPayoutMatchStatus.MATCHED:
            matched += 1
        elif line.match_status == BookingPayoutMatchStatus.UNMATCHED:
            unmatched += 1
        elif line.match_status == BookingPayoutMatchStatus.DUPLICATE:
            duplicates += 1

        sync_result = results_by_line.get(line.pk)
        if sync_result is None:
            continue

        if sync_result.result == "SUCCESS":
            applied += 1
            line_results.append(
                LineApplyResult(
                    line_number=line.line_number,
                    booking_number=line.booking_number,
                    action="applied",
                )
            )
        elif sync_result.result == "NO_CHANGES":
            skipped += 1
            line_results.append(
                LineApplyResult(
                    line_number=line.line_number,
                    booking_number=line.booking_number,
                    action="skipped",
                    message="No changes",
                )
            )
        else:
            errors += 1
            message = sync_result.error_code.label if sync_result.error_code else "Failed"
            line_results.append(
                LineApplyResult(
                    line_number=line.line_number,
                    booking_number=line.booking_number,
                    action="error",
                    message=message,
                )
            )

    result = PayoutImportResult(
        parsed=lines.count(),
        matched=matched,
        unmatched=unmatched,
        duplicates=duplicates,
        applied=applied,
        skipped=skipped,
        warnings=warnings,
        errors=errors,
        duration_ms=batch_result.duration_ms,
        line_results=line_results,
    )

    BookingPayoutImport.objects.filter(pk=import_id).update(
        summary_snapshot=result.as_dict()
    )

    return result
