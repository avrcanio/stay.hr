from decimal import Decimal


def compute_owner_net(
    amount: Decimal | None,
    commission_amount: Decimal | None,
) -> Decimal | None:
    """
    Owner net for a single reservation: gross minus Stay.hr commission.

    Semantics:
    - amount: reservation gross (bruto)
    - commission_amount: Stay.hr commission (provizija)
    - result: owner net (neto vlasniku)

    Intentionally does NOT account for:
    - Booking.com payout net
    - payment service fees
    - payout corrections
    - withholding or taxes

    For Booking.com payout amounts, use booking_payout_net on Reservation.
    For property report row aggregation, see property_financial_report._row_net
    (different None-handling for totals).
    """
    if amount is None or commission_amount is None:
        return None

    return amount - commission_amount


def format_money_amount(value: Decimal) -> str:
    """Format a money amount with exactly two decimal places."""
    return format(value.quantize(Decimal("0.01")), "f")
