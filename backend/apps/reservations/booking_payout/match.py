from __future__ import annotations

from decimal import Decimal

from apps.properties.models import Property
from apps.reservations.booking_payout.types import (
    BookingPayoutRowDTO,
    PayoutPreviewLine,
    warning_entry,
)
from apps.reservations.booking_payout_models import (
    BookingPayoutMatchStatus,
    BookingPayoutWarningSeverity,
)
from apps.reservations.channel_sync import find_reservation_for_channel_merge
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

_AMOUNT_TOLERANCE = Decimal("0.01")


def _amounts_equal(a: Decimal | None, b: Decimal) -> bool:
    if a is None:
        return False
    return abs(a - b) <= _AMOUNT_TOLERANCE


def match_booking_payout_rows(
    rows: list[BookingPayoutRowDTO],
    *,
    tenant: Tenant,
    property_obj: Property,
) -> list[PayoutPreviewLine]:
    seen_booking_numbers: dict[str, int] = {}
    preview_lines: list[PayoutPreviewLine] = []

    for row in rows:
        warnings: dict[str, dict] = {}
        match_status = BookingPayoutMatchStatus.MATCHED
        reservation: Reservation | None = None

        if row.booking_number in seen_booking_numbers:
            match_status = BookingPayoutMatchStatus.DUPLICATE
            warnings["duplicate"] = warning_entry(
                BookingPayoutWarningSeverity.ERROR,
                message="Duplicate booking number in payout file",
            )
        else:
            seen_booking_numbers[row.booking_number] = row.line_number
            reservation = find_reservation_for_channel_merge(
                tenant=tenant,
                booking_code=row.booking_number,
                external_id=row.booking_number,
            )
            if reservation is None:
                match_status = BookingPayoutMatchStatus.UNMATCHED
                warnings["match"] = warning_entry(
                    BookingPayoutWarningSeverity.ERROR,
                    message="Reservation not found for booking number",
                )
            elif reservation.property_id != property_obj.id:
                match_status = BookingPayoutMatchStatus.UNMATCHED
                warnings["match"] = warning_entry(
                    BookingPayoutWarningSeverity.ERROR,
                    message="Reservation belongs to a different property",
                )
                reservation = None
            else:
                _compare_reservation_fields(row, reservation, warnings)

        if row.service_fee > 0:
            warnings.setdefault(
                "service_fee",
                warning_entry(
                    BookingPayoutWarningSeverity.INFO,
                    csv=row.service_fee,
                    message="Payments service fee present",
                ),
            )

        preview_lines.append(
            PayoutPreviewLine(
                dto=row,
                match_status=match_status,
                reservation_id=reservation.pk if reservation else None,
                warnings=warnings,
            )
        )

    return preview_lines


def _compare_reservation_fields(
    row: BookingPayoutRowDTO,
    reservation: Reservation,
    warnings: dict[str, dict],
) -> None:
    if not _amounts_equal(reservation.amount, row.gross_amount):
        warnings["gross"] = warning_entry(
            BookingPayoutWarningSeverity.WARNING,
            reservation=reservation.amount,
            csv=row.gross_amount,
            message="Gross amount mismatch",
        )

    if reservation.commission_amount is not None and not _amounts_equal(
        reservation.commission_amount, row.commission_amount
    ):
        warnings["commission"] = warning_entry(
            BookingPayoutWarningSeverity.WARNING,
            reservation=reservation.commission_amount,
            csv=row.commission_amount,
            message="Commission amount mismatch",
        )
    elif reservation.commission_amount is None and row.commission_amount > 0:
        warnings["commission"] = warning_entry(
            BookingPayoutWarningSeverity.WARNING,
            reservation="",
            csv=row.commission_amount,
            message="Commission missing on reservation",
        )

    if reservation.check_in != row.check_in:
        warnings["check_in"] = warning_entry(
            BookingPayoutWarningSeverity.WARNING,
            reservation=reservation.check_in,
            csv=row.check_in,
            message="Check-in date mismatch",
        )

    if reservation.check_out != row.check_out:
        warnings["check_out"] = warning_entry(
            BookingPayoutWarningSeverity.WARNING,
            reservation=reservation.check_out,
            csv=row.check_out,
            message="Check-out date mismatch",
        )

    expected_net = row.gross_amount - row.commission_amount
    if abs(expected_net - row.net_amount) > _AMOUNT_TOLERANCE:
        warnings["net_formula"] = warning_entry(
            BookingPayoutWarningSeverity.INFO,
            message="Net differs from gross minus commission (service fee may apply)",
            csv=row.net_amount,
        )
