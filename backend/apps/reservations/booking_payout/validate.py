from __future__ import annotations

from apps.reservations.booking_payout.types import BookingPayoutRowDTO


class BookingPayoutValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        Exception.__init__(self, "; ".join(errors))


def validate_booking_payout_rows(rows: list[BookingPayoutRowDTO]) -> None:
    errors: list[str] = []
    if not rows:
        errors.append("No rows to validate")
        raise BookingPayoutValidationError(errors)

    payout_ids = {row.payout_id for row in rows}
    if len(payout_ids) != 1:
        errors.append(f"Inconsistent payout IDs in file: {sorted(payout_ids)}")

    payout_dates = {row.payout_date for row in rows}
    if len(payout_dates) != 1:
        errors.append(f"Inconsistent payout dates in file: {sorted(payout_dates)}")

    currencies = {row.currency for row in rows}
    if len(currencies) != 1:
        errors.append(f"Inconsistent currencies in file: {sorted(currencies)}")

    for row in rows:
        if row.gross_amount < 0:
            errors.append(f"Line {row.line_number}: negative gross amount")
        if row.commission_amount < 0:
            errors.append(f"Line {row.line_number}: negative commission amount")
        if row.service_fee < 0:
            errors.append(f"Line {row.line_number}: negative service fee")
        if row.check_out < row.check_in:
            errors.append(f"Line {row.line_number}: check-out before check-in")

    if errors:
        raise BookingPayoutValidationError(errors)
