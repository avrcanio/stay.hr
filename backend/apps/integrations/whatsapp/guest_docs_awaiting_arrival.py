"""Guest WhatsApp after docs apply on arrival day — without automatic check-in."""

from __future__ import annotations

import logging

from apps.communications.guest_compose import (
    HINT_DOCS_AWAITING_ARRIVAL,
    render_docs_awaiting_arrival_message,
)
from apps.communications.models import GuestMessageChannel, GuestMessageDraft, GuestMessageIntent
from apps.core.timezone import property_local_now
from apps.integrations.whatsapp.whatsapp_operator_service import (
    _send_checkin_complete_entrance_image,
)
from apps.integrations.whatsapp.evisitor_reply import _send_reservation_whatsapp_text
from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)


def _docs_awaiting_arrival_sent_today(reservation: Reservation) -> bool:
    now = property_local_now(reservation.property)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return GuestMessageDraft.objects.filter(
        reservation=reservation,
        hint=HINT_DOCS_AWAITING_ARRIVAL,
        sent_at__gte=start_of_day,
    ).exists()


def docs_awaiting_arrival_already_sent(reservation: Reservation) -> bool:
    return GuestMessageDraft.objects.filter(
        reservation=reservation,
        hint=HINT_DOCS_AWAITING_ARRIVAL,
    ).exists()


def notify_guest_docs_awaiting_arrival(reservation: Reservation) -> dict:
    """Send docs-saved + entrance/parking/WiFi message; idempotent once per reservation/day."""
    if _docs_awaiting_arrival_sent_today(reservation):
        return {"channel": "none", "status": "already_sent"}

    body = render_docs_awaiting_arrival_message(reservation)
    wa_result = _send_reservation_whatsapp_text(
        reservation=reservation,
        body=body,
        hint=HINT_DOCS_AWAITING_ARRIVAL,
    )
    if wa_result.get("status") != "sent":
        return {"channel": "none", **wa_result}

    entrance_image = _send_checkin_complete_entrance_image(
        reservation,
        hint=HINT_DOCS_AWAITING_ARRIVAL,
    )
    return {"channel": "whatsapp", **wa_result, "entrance_image": entrance_image}
