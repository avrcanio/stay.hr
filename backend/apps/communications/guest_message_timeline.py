"""Unified guest message timeline for a reservation (all channels)."""

from __future__ import annotations

from apps.communications.models import (
    GuestInboundMessage,
    GuestMessageChannel,
    GuestOutboundMessage,
    GuestOutboundMessageStatus,
)
from apps.integrations.models import ChannexMessage, WhatsAppMessage
from apps.reservations.models import DocumentIntakeJob, Reservation

WA_ID_OFFSET = 2_000_000_000
CHANNEX_ID_OFFSET = 3_000_000_000
INBOUND_ID_OFFSET = 4_000_000_000

_MEDIA_PREVIEW = {
    "image": "📷 Dokument poslan",
    "document": "📎 Datoteka poslana",
}

_OUTBOUND_IMAGE_PREVIEW = "📷 Slika poslana"


def document_intake_image_url(job_id: int, index: int = 0) -> str:
    return f"/api/v1/reception/document-intake/jobs/{job_id}/images/{index}/"


def whatsapp_message_media_url(message_id: int) -> str:
    return f"/api/v1/reception/whatsapp-messages/{message_id}/media/"


def media_kind_for_message_type(message_type: str) -> str | None:
    mt = (message_type or "").strip().lower()
    if mt in {"image", "document"}:
        return mt
    return None


def whatsapp_display_body(msg: WhatsAppMessage) -> str:
    body = (msg.body or "").strip()
    if body:
        return body
    return _MEDIA_PREVIEW.get(msg.message_type, "Poruka (WhatsApp)")


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
        "message_type": "text",
        "document_intake_job_id": None,
        "media_url": None,
        "media_kind": None,
    }


def _whatsapp_media_fields(msg: WhatsAppMessage, job_id: int | None) -> tuple[str | None, str | None]:
    message_type = msg.message_type or "text"
    media_kind = media_kind_for_message_type(message_type)
    if not media_kind:
        return None, None
    if getattr(msg, "media_file", None) and msg.media_file:
        return whatsapp_message_media_url(msg.pk), media_kind
    if job_id is not None:
        return document_intake_image_url(job_id), media_kind
    return None, media_kind


def serialize_whatsapp(msg: WhatsAppMessage) -> dict:
    job_id = (
        DocumentIntakeJob.objects.filter(whatsapp_message_id=msg.pk)
        .values_list("pk", flat=True)
        .first()
    )
    is_outbound = msg.direction == WhatsAppMessage.Direction.OUTBOUND
    media_url, media_kind = _whatsapp_media_fields(msg, job_id)
    body = whatsapp_display_body(msg)
    if is_outbound and (msg.message_type or "") == "image" and not (msg.body or "").strip():
        body = _OUTBOUND_IMAGE_PREVIEW
    return {
        "id": WA_ID_OFFSET + msg.pk,
        "source": "whatsapp",
        "direction": msg.direction,
        "channel": "whatsapp",
        "body_text": body,
        "created_at": msg.created_at.isoformat(),
        "status": "sent" if is_outbound else None,
        "sent_by_name": None,
        "from_email": None,
        "wa_me_url": None,
        "message_type": msg.message_type or "text",
        "document_intake_job_id": job_id,
        "media_url": media_url,
        "media_kind": media_kind,
    }


def _whatsapp_outbound_mirrors_guest_outbound(
    outbound: GuestOutboundMessage,
    whatsapp_rows: list[WhatsAppMessage],
) -> bool:
    """True when a WhatsAppMessage row already represents this API/handoff send."""
    body = (outbound.body_text or "").strip()
    if not body:
        return False
    for msg in whatsapp_rows:
        if msg.direction != WhatsAppMessage.Direction.OUTBOUND:
            continue
        if (msg.body or "").strip() != body:
            continue
        delta = abs((msg.created_at - outbound.created_at).total_seconds())
        if delta <= 5:
            return True
    return False


def serialize_inbound(inbound: GuestInboundMessage) -> dict:
    return {
        "id": INBOUND_ID_OFFSET + inbound.pk,
        "source": "inbound",
        "direction": "inbound",
        "channel": inbound.channel,
        "body_text": inbound.body_text or "",
        "created_at": inbound.created_at.isoformat(),
        "status": None,
        "sent_by_name": None,
        "from_email": inbound.from_email or None,
        "wa_me_url": None,
        "message_type": "text",
        "document_intake_job_id": None,
        "media_url": None,
        "media_kind": None,
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
        "message_type": "text",
        "document_intake_job_id": None,
        "media_url": None,
        "media_kind": None,
    }


def timeline_for_reservation(reservation: Reservation) -> list[dict]:
    rows: list[tuple[str, dict]] = []

    whatsapp_rows = list(
        WhatsAppMessage.objects.filter(reservation=reservation).order_by("created_at", "pk")
    )

    for outbound in GuestOutboundMessage.objects.filter(reservation=reservation).select_related(
        "api_application"
    ):
        if (
            outbound.channel == GuestMessageChannel.WHATSAPP
            and outbound.status == GuestOutboundMessageStatus.SENT
            and _whatsapp_outbound_mirrors_guest_outbound(outbound, whatsapp_rows)
        ):
            continue
        rows.append((outbound.created_at.isoformat(), serialize_outbound(outbound)))

    for msg in whatsapp_rows:
        rows.append((msg.created_at.isoformat(), serialize_whatsapp(msg)))

    for msg in ChannexMessage.objects.filter(reservation=reservation):
        if (msg.body or "").strip():
            rows.append((msg.created_at.isoformat(), serialize_channex(msg)))

    for msg in GuestInboundMessage.objects.filter(reservation=reservation):
        if (msg.body_text or "").strip():
            rows.append((msg.created_at.isoformat(), serialize_inbound(msg)))

    rows.sort(key=lambda r: r[0])
    return [item for _, item in rows]


def last_timeline_entry(reservation: Reservation) -> dict | None:
    timeline = timeline_for_reservation(reservation)
    return timeline[-1] if timeline else None
