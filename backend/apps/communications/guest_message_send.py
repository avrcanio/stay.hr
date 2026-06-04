"""Send guest messages via email SMTP or WhatsApp handoff."""

from __future__ import annotations

import logging
from urllib.parse import quote

from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from apps.communications.guest_email import (
    _email_context,
    _guest_recipient,
    _language_for_reservation,
    _sender_for_reservation,
    _send_guest_email,
)
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestOutboundMessage,
    GuestOutboundMessageStatus,
)
from apps.integrations.whatsapp.phone import normalize_phone
from apps.reservations.models import Reservation
from apps.tenants.models import ApiApplication

logger = logging.getLogger(__name__)

MAPS_LINK = "https://maps.app.goo.gl/BN15CcMmmAapmjUs7"


def guest_phone_number(reservation: Reservation) -> str:
    return (reservation.booker_phone or "").strip()


def build_wa_me_url(phone_digits: str, body_text: str) -> str:
    digits = normalize_phone(phone_digits)
    if not digits:
        return ""
    encoded = quote(body_text or "", safe="")
    return f"https://wa.me/{digits}?text={encoded}"


def build_message_channels(reservation: Reservation) -> dict:
    email = _guest_recipient(reservation)
    phone_raw = guest_phone_number(reservation)
    phone_wa = normalize_phone(phone_raw)

    return {
        "email": {
            "available": bool(email),
            "to": email or "",
        },
        "whatsapp": {
            "available": bool(phone_wa),
            "phone_raw": phone_raw,
            "phone_wa": phone_wa,
            "wa_me_url": build_wa_me_url(phone_wa, "") if phone_wa else "",
        },
    }


def default_email_subject(reservation: Reservation) -> str:
    code = (reservation.booking_code or reservation.external_id or "").strip()
    lang = _language_for_reservation(reservation)
    if code:
        if lang == "hr":
            return f"Poruka o rezervaciji {code}"
        return f"Message about booking {code}"
    if lang == "hr":
        return f"Poruka o rezervaciji #{reservation.pk}"
    return f"Message about reservation #{reservation.pk}"


def send_guest_text_email(
    reservation: Reservation,
    body_text: str,
    *,
    subject: str | None = None,
) -> dict:
    """Send plain-text email to guest; returns {sent, to?, reason?}."""
    recipient = _guest_recipient(reservation)
    if not recipient:
        return {"sent": False, "reason": "no_recipient"}

    text = (body_text or "").strip()
    if not text:
        return {"sent": False, "reason": "empty_body"}

    subj = (subject or default_email_subject(reservation)).strip()
    from_header, reply_to = _sender_for_reservation(reservation)
    message = EmailMultiAlternatives(
        subject=subj,
        body=text,
        from_email=from_header,
        to=[recipient],
        reply_to=[reply_to] if reply_to else None,
    )
    try:
        if not _send_guest_email(message, reservation):
            return {"sent": False, "reason": "smtp_not_configured"}
    except Exception as exc:
        logger.exception(
            "guest text email failed",
            extra={"reservation_id": reservation.pk},
        )
        return {"sent": False, "reason": "send_failed", "error": str(exc)}

    logger.info(
        "guest text email sent",
        extra={"reservation_id": reservation.pk, "to": recipient},
    )
    return {"sent": True, "to": recipient}


def send_guest_message(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    channel: str,
    body_text: str,
    api_application: ApiApplication | None,
    subject: str | None = None,
) -> GuestOutboundMessage:
    """Send via email or record WhatsApp handoff."""
    text = (body_text or "").strip()
    if not text:
        raise ValueError("body_text is required")

    if channel == GuestMessageChannel.EMAIL:
        return _send_email_channel(
            reservation=reservation,
            draft=draft,
            body_text=text,
            api_application=api_application,
            subject=subject,
        )
    if channel == GuestMessageChannel.WHATSAPP:
        return _send_whatsapp_handoff(
            reservation=reservation,
            draft=draft,
            body_text=text,
            api_application=api_application,
        )
    raise ValueError(f"Unsupported channel: {channel}")


def _send_email_channel(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    body_text: str,
    api_application: ApiApplication | None,
    subject: str | None,
) -> GuestOutboundMessage:
    recipient = _guest_recipient(reservation) or ""
    outbound = GuestOutboundMessage.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        draft=draft,
        channel=GuestMessageChannel.EMAIL,
        body_text=body_text,
        status=GuestOutboundMessageStatus.QUEUED,
        to_email=recipient,
        api_application=api_application,
    )

    result = send_guest_text_email(reservation, body_text, subject=subject)
    if result.get("sent"):
        outbound.status = GuestOutboundMessageStatus.SENT
        outbound.error_message = ""
    else:
        outbound.status = GuestOutboundMessageStatus.FAILED
        outbound.error_message = result.get("reason") or result.get("error") or "send_failed"

    outbound.save(update_fields=["status", "error_message"])

    draft.final_body_text = body_text
    draft.channel = GuestMessageChannel.EMAIL
    update_fields = ["final_body_text", "channel"]
    if outbound.status == GuestOutboundMessageStatus.SENT:
        draft.sent_at = timezone.now()
        update_fields.append("sent_at")
    draft.save(update_fields=update_fields)

    return outbound


def _send_whatsapp_handoff(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    body_text: str,
    api_application: ApiApplication | None,
) -> GuestOutboundMessage:
    phone_raw = guest_phone_number(reservation)
    phone_wa = normalize_phone(phone_raw)
    if not phone_wa:
        raise ValueError("no_phone")

    wa_me_url = build_wa_me_url(phone_wa, body_text)
    outbound = GuestOutboundMessage.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        draft=draft,
        channel=GuestMessageChannel.WHATSAPP,
        body_text=body_text,
        status=GuestOutboundMessageStatus.HANDOFF_WHATSAPP,
        to_phone=phone_raw,
        wa_me_url=wa_me_url,
        api_application=api_application,
    )

    now = timezone.now()
    draft.final_body_text = body_text
    draft.channel = GuestMessageChannel.WHATSAPP
    draft.sent_at = now
    draft.save(update_fields=["final_body_text", "channel", "sent_at"])

    return outbound
