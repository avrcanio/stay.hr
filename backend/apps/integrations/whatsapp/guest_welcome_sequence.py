"""WhatsApp welcome: text → entrance image → ask arrival time."""

from __future__ import annotations

import logging

from apps.integrations.whatsapp.evisitor_reply import _send_reservation_whatsapp_text
from apps.integrations.whatsapp.whatsapp_operator_service import (
    _send_checkin_complete_entrance_image,
    send_whatsapp_ask_arrival_time,
)
from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)


def send_guest_welcome_entrance_and_ask_arrival(
    reservation: Reservation,
    *,
    body: str,
    hint: str,
) -> dict:
    """Send welcome text, entrance photo, then a separate ask-arrival message."""
    wa_result = _send_reservation_whatsapp_text(
        reservation=reservation,
        body=body,
        hint=hint,
    )
    if wa_result.get("status") != "sent":
        return wa_result

    entrance_image = _send_checkin_complete_entrance_image(
        reservation,
        hint=hint,
    )
    ask_result = send_whatsapp_ask_arrival_time(reservation)

    return {
        "channel": "whatsapp",
        **wa_result,
        "entrance_image": entrance_image,
        "ask_arrival": ask_result,
    }
