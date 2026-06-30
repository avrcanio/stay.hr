"""Inbound hook: update conversation language from guest messages."""

from __future__ import annotations

from datetime import datetime

from apps.communications.conversation_language_store import maybe_update
from apps.communications.language_detection import detect
from apps.reservations.models import Reservation


def on_guest_inbound_message(
    reservation: Reservation,
    *,
    body: str,
    channel: str,
    received_at: datetime | None = None,
) -> None:
    candidate = detect(body)
    maybe_update(
        reservation,
        candidate,
        channel=channel,
        received_at=received_at,
    )
