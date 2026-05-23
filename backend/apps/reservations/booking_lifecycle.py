"""Web booking lifecycle: pending → expected/refused after Smoobu block sync."""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)

WEB_BOOKING_SOURCE = "api"


def is_web_pending_booking(reservation: Reservation) -> bool:
    return (
        reservation.status == Reservation.Status.PENDING
        and not (reservation.import_source or "").strip()
        and (reservation.source or WEB_BOOKING_SOURCE).strip().lower() == WEB_BOOKING_SOURCE
    )


def confirm_web_booking(reservation_id: int) -> bool:
    """Promote pending web booking to expected after Smoobu block success."""
    reservation = Reservation.objects.filter(pk=reservation_id).first()
    if reservation is None or not is_web_pending_booking(reservation):
        return False

    now = timezone.now()
    Reservation.objects.filter(pk=reservation_id).update(
        status=Reservation.Status.EXPECTED,
        booked_at=now,
        updated_at=now,
    )

    from apps.communications.tasks import send_guest_booking_confirmed_email
    from apps.core.tasks import notify_new_reservation

    send_guest_booking_confirmed_email.delay(reservation_id)
    notify_new_reservation.delay(reservation_id)
    logger.info(
        "web booking confirmed",
        extra={"reservation_id": reservation_id},
    )
    return True


def refuse_web_booking(reservation_id: int, *, reason: str = "") -> bool:
    """Mark pending web booking as refused and notify guest."""
    reservation = Reservation.objects.filter(pk=reservation_id).first()
    if reservation is None or not is_web_pending_booking(reservation):
        return False

    from apps.integrations.smoobu.reservation_blocking_service import (
        remove_reservation_smoobu_blocks,
    )

    try:
        remove_reservation_smoobu_blocks(reservation)
    except Exception:
        logger.exception(
            "failed to cleanup blocks while refusing web booking",
            extra={"reservation_id": reservation_id},
        )

    now = timezone.now()
    Reservation.objects.filter(pk=reservation_id).update(
        status=Reservation.Status.REFUSED,
        updated_at=now,
    )

    from apps.communications.tasks import send_guest_booking_refused_email

    send_guest_booking_refused_email.delay(reservation_id, reason=reason)
    logger.info(
        "web booking refused",
        extra={"reservation_id": reservation_id, "reason": reason},
    )
    return True
