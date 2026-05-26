"""Web booking lifecycle: pending → expected/refused after channel outbound sync."""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.integrations.channel_manager.resolver import get_channel_manager
from apps.reservations.models import Reservation
from apps.tenants.models import ChannelManager

logger = logging.getLogger(__name__)

WEB_BOOKING_SOURCE = "api"


def is_web_pending_booking(reservation: Reservation) -> bool:
    return (
        reservation.status == Reservation.Status.PENDING
        and not (reservation.import_source or "").strip()
        and (reservation.source or WEB_BOOKING_SOURCE).strip().lower() == WEB_BOOKING_SOURCE
    )


def confirm_web_booking(reservation_id: int) -> bool:
    """Promote pending web booking to expected after outbound channel sync success."""
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

    manager = get_channel_manager(reservation.tenant)
    if manager != ChannelManager.NONE:
        try:
            from apps.integrations.channel_manager.dispatch import remove_reservation_outbound

            remove_reservation_outbound(reservation)
        except Exception:
            logger.exception(
                "failed to cleanup outbound blocks while refusing web booking",
                extra={"reservation_id": reservation_id},
            )

    from apps.integrations.models import UnitAvailabilityBlock

    UnitAvailabilityBlock.objects.filter(reservation=reservation).delete()

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
