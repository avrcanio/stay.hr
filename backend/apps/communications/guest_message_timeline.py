"""Unified guest message timeline for a reservation (all channels)."""

from __future__ import annotations

from apps.communications.models import GuestOutboundMessage
from apps.integrations.models import ChannexMessage, WhatsAppMessage
from apps.reservations.models import Reservation

WA_ID_OFFSET = 2_000_000_000
CHANNEX_ID_OFFSET = 3_000_000_000


def serialize_outbound(outbound: GuestOutboundMessage) -> dict:
    app = outbound.api_application
    return {
        "id": outbound.pk,
        "source": "outbound",
        "direction": "outbound",
        "channel": outbound.channel,
        "body_text": outbound.body_text,
        "created_at": outbound.created_at.isoformat(),
        "status": outbound.status,
        "sent_by_name": app.name if app else None,
        "from_email": None,
        "wa_me_url": outbound.wa_me_url or None,
    }


def serialize_whatsapp(msg: WhatsAppMessage) -> dict:
    return {
        "id": WA_ID_OFFSET + msg.pk,
        "source": "whatsapp",
        "direction": msg.direction,
        "channel": "whatsapp",
        "body_text": msg.body or "",
        "created_at": msg.created_at.isoformat(),
        "status": None,
        "sent_by_name": None,
        "from_email": None,
        "wa_me_url": None,
    }


def serialize_channex(msg: ChannexMessage) -> dict:
    direction = "inbound" if msg.sender == ChannexMessage.Sender.GUEST else "outbound"
    return {
        "id": CHANNEX_ID_OFFSET + msg.pk,
        "source": "booking",
        "direction": direction,
        "channel": "booking",
        "body_text": msg.body or "",
        "created_at": msg.created_at.isoformat(),
        "status": None,
        "sent_by_name": None,
        "from_email": None,
        "wa_me_url": None,
    }


def timeline_for_reservation(reservation: Reservation) -> list[dict]:
    rows: list[tuple[str, dict]] = []

    for outbound in GuestOutboundMessage.objects.filter(reservation=reservation).select_related(
        "api_application"
    ):
        rows.append((outbound.created_at.isoformat(), serialize_outbound(outbound)))

    for msg in WhatsAppMessage.objects.filter(reservation=reservation):
        if (msg.body or "").strip():
            rows.append((msg.created_at.isoformat(), serialize_whatsapp(msg)))

    for msg in ChannexMessage.objects.filter(reservation=reservation):
        if (msg.body or "").strip():
            rows.append((msg.created_at.isoformat(), serialize_channex(msg)))

    rows.sort(key=lambda r: r[0])
    return [item for _, item in rows]


def last_timeline_entry(reservation: Reservation) -> dict | None:
    timeline = timeline_for_reservation(reservation)
    return timeline[-1] if timeline else None
