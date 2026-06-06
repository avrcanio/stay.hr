"""Send guest messages via email SMTP, WhatsApp API (360dialog), or WhatsApp handoff."""

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
from apps.integrations.channex.ari_service import get_active_channex_integration
from apps.integrations.channex.booking_service import parse_channex_booking_id
from apps.integrations.channex.exceptions import ChannexBookingIngestError
from apps.integrations.channex.message_service import send_message_for_reservation
from apps.integrations.channel_manager.resolver import get_channel_manager
from apps.integrations.models import ChannexMessage, IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.client import WhatsAppApiError, extract_outbound_wamid, send_text_message
from apps.integrations.whatsapp.config import is_360dialog_provider
from apps.integrations.whatsapp.integration_lookup import get_active_whatsapp_integration
from apps.integrations.whatsapp.phone import normalize_phone
from apps.reservations.models import Reservation
from apps.tenants.models import ApiApplication, ChannelManager

logger = logging.getLogger(__name__)

MAPS_LINK = "https://maps.app.goo.gl/BN15CcMmmAapmjUs7"

# Pre-filled WhatsApp text limit (chars before URL encoding).
WA_ME_BODY_MAX_LEN = 1500


def guest_phone_number(reservation: Reservation) -> str:
    return (reservation.booker_phone or "").strip()


def truncate_wa_me_body(body_text: str) -> str:
    text = (body_text or "").strip()
    if len(text) <= WA_ME_BODY_MAX_LEN:
        return text
    suffix = "…"
    return text[: WA_ME_BODY_MAX_LEN - len(suffix)].rstrip() + suffix


def build_wa_me_url(phone_digits: str, body_text: str) -> str:
    digits = normalize_phone(phone_digits)
    if not digits:
        return ""
    encoded = quote(truncate_wa_me_body(body_text), safe="")
    return f"https://wa.me/{digits}?text={encoded}"


def _booking_channel_available(reservation: Reservation) -> bool:
    if get_channel_manager(reservation.tenant) != ChannelManager.CHANNEX:
        return False
    if reservation.import_source != "channex":
        return False
    if not parse_channex_booking_id(reservation.external_id):
        return False
    return IntegrationConfig.objects.filter(
        tenant=reservation.tenant,
        provider=IntegrationConfig.Provider.CHANNEX,
        is_active=True,
    ).exists()


def build_message_channels(reservation: Reservation) -> dict:
    email = _guest_recipient(reservation)
    phone_raw = guest_phone_number(reservation)
    phone_wa = normalize_phone(phone_raw)
    booking_available = _booking_channel_available(reservation)
    _, whatsapp_runtime = get_active_whatsapp_integration(reservation.tenant)
    whatsapp_api_send = bool(
        whatsapp_runtime
        and is_360dialog_provider(whatsapp_runtime.provider)
        and whatsapp_runtime.send_credentials_ok()
    )

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
            "api_send": whatsapp_api_send,
        },
        "booking": {
            "available": booking_available,
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
) -> GuestOutboundMessage | ChannexMessage:
    """Send via email, WhatsApp handoff, or Channex Booking.com messages."""
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
        return _send_whatsapp_channel(
            reservation=reservation,
            draft=draft,
            body_text=text,
            api_application=api_application,
        )
    if channel == GuestMessageChannel.BOOKING:
        return _send_booking_channel(
            reservation=reservation,
            draft=draft,
            body_text=text,
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


def _send_whatsapp_channel(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    body_text: str,
    api_application: ApiApplication | None,
) -> GuestOutboundMessage:
    integration, runtime = get_active_whatsapp_integration(reservation.tenant)
    if (
        integration is not None
        and runtime is not None
        and is_360dialog_provider(runtime.provider)
        and runtime.send_credentials_ok()
    ):
        return _send_whatsapp_api(
            reservation=reservation,
            draft=draft,
            body_text=body_text,
            api_application=api_application,
            integration=integration,
            runtime=runtime,
        )
    return _send_whatsapp_handoff(
        reservation=reservation,
        draft=draft,
        body_text=body_text,
        api_application=api_application,
    )


def _send_whatsapp_api(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    body_text: str,
    api_application: ApiApplication | None,
    integration: IntegrationConfig,
    runtime,
) -> GuestOutboundMessage:
    phone_raw = guest_phone_number(reservation)
    phone_wa = normalize_phone(phone_raw)
    if not phone_wa:
        raise ValueError("no_phone")

    outbound = GuestOutboundMessage.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        draft=draft,
        channel=GuestMessageChannel.WHATSAPP,
        body_text=body_text,
        status=GuestOutboundMessageStatus.QUEUED,
        to_phone=phone_raw,
        api_application=api_application,
    )

    try:
        response = send_text_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=phone_wa,
            body=body_text,
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        outbound.status = GuestOutboundMessageStatus.FAILED
        outbound.error_message = str(exc)
        outbound.save(update_fields=["status", "error_message"])
        raise ValueError(str(exc)) from exc

    wamid = extract_outbound_wamid(response)
    if wamid:
        WhatsAppMessage.objects.create(
            tenant_id=reservation.tenant_id,
            integration=integration,
            reservation=reservation,
            wamid=wamid,
            wa_id=phone_wa,
            phone_number_id=runtime.phone_number_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="text",
            body=body_text,
            raw_payload=response,
        )

    now = timezone.now()
    outbound.status = GuestOutboundMessageStatus.SENT
    outbound.error_message = ""
    outbound.save(update_fields=["status", "error_message"])

    draft.final_body_text = body_text
    draft.channel = GuestMessageChannel.WHATSAPP
    draft.sent_at = now
    draft.save(update_fields=["final_body_text", "channel", "sent_at"])

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


def _send_booking_channel(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    body_text: str,
) -> ChannexMessage:
    if not _booking_channel_available(reservation):
        raise ValueError("booking_channel_unavailable")

    integration = get_active_channex_integration(reservation.tenant.slug)
    try:
        row = send_message_for_reservation(integration, reservation, body_text)
    except ChannexBookingIngestError as exc:
        raise ValueError(str(exc)) from exc

    now = timezone.now()
    draft.final_body_text = body_text
    draft.channel = GuestMessageChannel.BOOKING
    draft.sent_at = now
    draft.save(update_fields=["final_body_text", "channel", "sent_at"])

    return row
