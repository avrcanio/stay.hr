from apps.integrations.evisitor.service import checkout_reservation_guests_in_evisitor
from apps.integrations.evisitor.summary import evisitor_summary_for_reservation
from apps.reservations.models import Reservation


class CheckoutBlockedError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def perform_reservation_checkout(
    reservation: Reservation,
    *,
    source: str = "manual",
) -> None:
    del source  # reserved for audit/logging

    if reservation.status != Reservation.Status.CHECKED_IN:
        raise CheckoutBlockedError(
            "invalid_status",
            f"Reservation status is {reservation.status}, expected checked_in.",
        )

    summary = evisitor_summary_for_reservation(reservation)
    if summary == "none":
        raise CheckoutBlockedError(
            "evisitor_none",
            "Checkout blocked: reservation has no guests.",
        )
    if summary != "complete":
        raise CheckoutBlockedError(
            "evisitor_incomplete",
            "Checkout blocked: eVisitor registration incomplete.",
        )

    checkout_reservation_guests_in_evisitor(reservation)
    reservation.status = Reservation.Status.CHECKED_OUT
    reservation.save(update_fields=["status", "updated_at"])
