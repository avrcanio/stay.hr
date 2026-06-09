"""Send guest messages via email SMTP, WhatsApp API (360dialog), or WhatsApp handoff."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.files.base import ContentFile

from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from apps.communications.guest_email import (
    _email_context,
    _guest_recipient,
    _language_for_reservation,
    _sender_for_reservation,
    _send_guest_email,
)
from apps.communications.guest_email_html import prepare_guest_email_bodies
from apps.communications.guest_compose_language import compose_language_for_reservation
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
    GuestOutboundMessage,
    GuestOutboundMessageStatus,
)
from apps.integrations.channex.ari_service import get_active_channex_integration
from apps.integrations.channex.booking_service import (
    _channex_booking_lookup_codes,
    parse_channex_booking_id,
)
from apps.integrations.channex.exceptions import ChannexBookingIngestError
from apps.integrations.channex.message_service import send_image_for_reservation, send_message_for_reservation
from apps.integrations.channel_manager.resolver import get_channel_manager
from apps.integrations.models import ChannexBookingRevision, ChannexMessage, IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.client import (
    WhatsAppApiError,
    extract_outbound_wamid,
    send_image_message,
    send_text_message,
    upload_media,
)
from apps.integrations.whatsapp.config import is_360dialog_provider
from apps.integrations.whatsapp.integration_lookup import get_active_whatsapp_integration
from apps.integrations.whatsapp.phone import normalize_phone
from apps.reservations.models import Reservation
from apps.tenants.models import ApiApplication, ChannelManager

logger = logging.getLogger(__name__)

MAPS_LINK = "https://maps.app.goo.gl/BN15CcMmmAapmjUs7"

# Pre-filled WhatsApp text limit (chars before URL encoding).
WA_ME_BODY_MAX_LEN = 1500
_OUTBOUND_IMAGE_BODY = "📷 Slika poslana"


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
    has_channex_link = bool(parse_channex_booking_id(reservation.external_id))
    if not has_channex_link:
        has_channex_link = bool(_channex_booking_lookup_codes(reservation)) or (
            ChannexBookingRevision.objects.filter(reservation=reservation).exists()
        )
    if not has_channex_link:
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

    email_available = bool(email)
    whatsapp_available = bool(phone_wa)

    if email_available:
        default_channel = GuestMessageChannel.EMAIL
    elif whatsapp_available:
        default_channel = GuestMessageChannel.WHATSAPP
    elif booking_available:
        default_channel = GuestMessageChannel.BOOKING
    else:
        default_channel = ""

    return {
        "email": {
            "available": email_available,
            "to": email or "",
        },
        "whatsapp": {
            "available": whatsapp_available,
            "phone_raw": phone_raw,
            "phone_wa": phone_wa,
            "wa_me_url": build_wa_me_url(phone_wa, "") if phone_wa else "",
            "api_send": whatsapp_api_send,
        },
        "booking": {
            "available": booking_available,
        },
        "default_channel": default_channel,
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
    body_html: str | None = None,
    attachment: tuple[str, bytes, str] | None = None,
) -> dict:
    """Send guest email via SMTP (no timeline record).

    Prefer :func:`send_guest_email_with_timeline_record` so the message appears in
    reception / Hospira guest threads.

    attachment: optional (filename, bytes, mime_type).
    """
    recipient = _guest_recipient(reservation)
    if not recipient:
        return {"sent": False, "reason": "no_recipient"}

    text = (body_text or "").strip()
    if not text and attachment is None:
        return {"sent": False, "reason": "empty_body"}

    subj = (subject or default_email_subject(reservation)).strip()
    from_header, reply_to = _sender_for_reservation(reservation)
    message = EmailMultiAlternatives(
        subject=subj,
        body=text or _OUTBOUND_IMAGE_BODY,
        from_email=from_header,
        to=[recipient],
        reply_to=[reply_to] if reply_to else None,
    )
    html = (body_html or "").strip()
    if html:
        message.attach_alternative(html, "text/html")
    if attachment is not None:
        filename, file_bytes, mime_type = attachment
        message.attach(filename, file_bytes, mime_type)
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


def send_guest_email_with_timeline_record(
    reservation: Reservation,
    body_text: str,
    *,
    subject: str | None = None,
    body_html: str | None = None,
    draft: GuestMessageDraft | None = None,
    api_application: ApiApplication | None = None,
    intent: str = GuestMessageIntent.CUSTOM,
    hint: str = "",
) -> GuestOutboundMessage:
    """Send guest SMTP email and record GuestOutboundMessage for unified timeline."""
    text, html_part = prepare_guest_email_bodies(body_text, body_html=body_html)
    recipient = _guest_recipient(reservation) or ""

    if draft is None:
        draft = GuestMessageDraft.objects.create(
            tenant_id=reservation.tenant_id,
            reservation=reservation,
            intent=intent,
            hint=hint,
            language=compose_language_for_reservation(reservation),
            llm_body_text=(body_text or "").strip(),
            final_body_text="",
            channel=GuestMessageChannel.EMAIL,
            api_application=api_application,
        )

    outbound = GuestOutboundMessage.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        draft=draft,
        channel=GuestMessageChannel.EMAIL,
        body_text=text,
        status=GuestOutboundMessageStatus.QUEUED,
        to_email=recipient,
        api_application=api_application,
    )

    result = send_guest_text_email(
        reservation,
        text,
        subject=subject,
        body_html=html_part,
    )
    if result.get("sent"):
        outbound.status = GuestOutboundMessageStatus.SENT
        outbound.error_message = ""
    else:
        outbound.status = GuestOutboundMessageStatus.FAILED
        outbound.error_message = result.get("reason") or result.get("error") or "send_failed"

    outbound.save(update_fields=["status", "error_message"])

    draft.final_body_text = text
    draft.channel = GuestMessageChannel.EMAIL
    update_fields = ["final_body_text", "channel"]
    if outbound.status == GuestOutboundMessageStatus.SENT:
        draft.sent_at = timezone.now()
        update_fields.append("sent_at")
    draft.save(update_fields=update_fields)

    return outbound


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
    return send_guest_email_with_timeline_record(
        reservation,
        body_text,
        subject=subject,
        draft=draft,
        api_application=api_application,
    )


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


def send_guest_whatsapp_image(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    uploaded_file,
    caption: str = "",
    api_application: ApiApplication | None,
) -> WhatsAppMessage:
    """Send image via 360dialog WhatsApp API; returns WhatsAppMessage row."""
    integration, runtime = get_active_whatsapp_integration(reservation.tenant)
    if integration is None or runtime is None:
        raise ValueError("whatsapp_not_configured")
    if not is_360dialog_provider(runtime.provider) or not runtime.send_credentials_ok():
        raise ValueError("whatsapp_api_send_unavailable")

    phone_raw = guest_phone_number(reservation)
    phone_wa = normalize_phone(phone_raw)
    if not phone_wa:
        raise ValueError("no_phone")

    file_bytes = uploaded_file.read()
    uploaded_file.seek(0)
    if not file_bytes:
        raise ValueError("empty_file")

    mime_type = getattr(uploaded_file, "content_type", None) or mimetypes.guess_type(
        getattr(uploaded_file, "name", "") or ""
    )[0] or "image/jpeg"
    if not mime_type.startswith("image/"):
        raise ValueError("unsupported_media_type")

    filename = getattr(uploaded_file, "name", None) or "image.jpg"

    outbound = GuestOutboundMessage.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        draft=draft,
        channel=GuestMessageChannel.WHATSAPP,
        body_text=(caption or "").strip() or _OUTBOUND_IMAGE_BODY,
        status=GuestOutboundMessageStatus.QUEUED,
        to_phone=phone_raw,
        api_application=api_application,
    )

    try:
        media_id = upload_media(
            file_bytes=file_bytes,
            mime_type=mime_type,
            filename=filename,
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
        response = send_image_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=phone_wa,
            media_id=media_id,
            caption=caption,
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        outbound.status = GuestOutboundMessageStatus.FAILED
        outbound.error_message = str(exc)
        outbound.save(update_fields=["status", "error_message"])
        raise ValueError(str(exc)) from exc

    wamid = extract_outbound_wamid(response) or f"local.outbound.image.{outbound.pk}"
    wa_message = WhatsAppMessage.objects.create(
        tenant_id=reservation.tenant_id,
        integration=integration,
        reservation=reservation,
        wamid=wamid,
        wa_id=phone_wa,
        phone_number_id=runtime.phone_number_id,
        direction=WhatsAppMessage.Direction.OUTBOUND,
        message_type="image",
        body=(caption or "").strip(),
        raw_payload=response,
    )
    wa_message.media_file.save(filename, ContentFile(file_bytes), save=True)

    now = timezone.now()
    outbound.status = GuestOutboundMessageStatus.SENT
    outbound.error_message = ""
    outbound.save(update_fields=["status", "error_message"])

    draft.final_body_text = (caption or "").strip() or _OUTBOUND_IMAGE_BODY
    draft.channel = GuestMessageChannel.WHATSAPP
    draft.sent_at = now
    draft.save(update_fields=["final_body_text", "channel", "sent_at"])

    return wa_message


def uzorita_entrance_image_path() -> Path:
    """Legacy fallback when Property.guest_info has no entrance_image."""
    return Path(settings.BASE_DIR) / "assets" / "whatsapp" / "uzorita_entrance.jpg"


def send_whatsapp_entrance_image_from_asset(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    caption: str = "",
    api_application: ApiApplication | None,
) -> WhatsAppMessage:
    """Send property entrance photo from guest_info asset (WhatsApp auto-reply after check-in)."""
    from apps.properties.guest_info import property_entrance_image_path

    path = property_entrance_image_path(reservation.property)
    if not path.is_file():
        raise ValueError("entrance_image_missing")

    integration, runtime = get_active_whatsapp_integration(reservation.tenant)
    if integration is None or runtime is None:
        raise ValueError("whatsapp_not_configured")
    if not is_360dialog_provider(runtime.provider) or not runtime.send_credentials_ok():
        raise ValueError("whatsapp_api_send_unavailable")

    phone_raw = guest_phone_number(reservation)
    phone_wa = normalize_phone(phone_raw)
    if not phone_wa:
        raise ValueError("no_phone")

    file_bytes = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    filename = path.name

    outbound = GuestOutboundMessage.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        draft=draft,
        channel=GuestMessageChannel.WHATSAPP,
        body_text=(caption or "").strip() or _OUTBOUND_IMAGE_BODY,
        status=GuestOutboundMessageStatus.QUEUED,
        to_phone=phone_raw,
        api_application=api_application,
    )

    try:
        media_id = upload_media(
            file_bytes=file_bytes,
            mime_type=mime_type,
            filename=filename,
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
        response = send_image_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=phone_wa,
            media_id=media_id,
            caption=caption,
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        outbound.status = GuestOutboundMessageStatus.FAILED
        outbound.error_message = str(exc)
        outbound.save(update_fields=["status", "error_message"])
        raise ValueError(str(exc)) from exc

    wamid = extract_outbound_wamid(response) or f"local.outbound.image.{outbound.pk}"
    wa_message = WhatsAppMessage.objects.create(
        tenant_id=reservation.tenant_id,
        integration=integration,
        reservation=reservation,
        wamid=wamid,
        wa_id=phone_wa,
        phone_number_id=runtime.phone_number_id,
        direction=WhatsAppMessage.Direction.OUTBOUND,
        message_type="image",
        body=(caption or "").strip(),
        raw_payload=response,
    )
    wa_message.media_file.save(filename, ContentFile(file_bytes), save=True)

    now = timezone.now()
    outbound.status = GuestOutboundMessageStatus.SENT
    outbound.error_message = ""
    outbound.save(update_fields=["status", "error_message"])

    draft.final_body_text = (caption or "").strip() or _OUTBOUND_IMAGE_BODY
    draft.channel = GuestMessageChannel.WHATSAPP
    draft.sent_at = now
    draft.save(update_fields=["final_body_text", "channel", "sent_at"])

    return wa_message


def send_guest_email_image(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    uploaded_file,
    caption: str = "",
    api_application: ApiApplication | None,
    subject: str | None = None,
) -> GuestOutboundMessage:
    """Send image attachment to guest via tenant SMTP."""
    recipient = _guest_recipient(reservation) or ""
    if not recipient:
        raise ValueError("no_recipient")

    file_bytes = uploaded_file.read()
    uploaded_file.seek(0)
    if not file_bytes:
        raise ValueError("empty_file")

    mime_type = getattr(uploaded_file, "content_type", None) or mimetypes.guess_type(
        getattr(uploaded_file, "name", "") or ""
    )[0] or "image/jpeg"
    if not mime_type.startswith("image/"):
        raise ValueError("unsupported_media_type")

    filename = getattr(uploaded_file, "name", None) or "image.jpg"
    raw_body = (caption or "").strip() or _OUTBOUND_IMAGE_BODY
    body_text, html_part = prepare_guest_email_bodies(raw_body)

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

    result = send_guest_text_email(
        reservation,
        body_text,
        subject=subject,
        body_html=html_part,
        attachment=(filename, file_bytes, mime_type),
    )
    if result.get("sent"):
        outbound.status = GuestOutboundMessageStatus.SENT
        outbound.error_message = ""
        outbound.media_file.save(filename, ContentFile(file_bytes), save=True)
    else:
        outbound.status = GuestOutboundMessageStatus.FAILED
        outbound.error_message = result.get("reason") or result.get("error") or "send_failed"
        outbound.save(update_fields=["status", "error_message"])
        raise ValueError(outbound.error_message)

    draft.final_body_text = body_text
    draft.channel = GuestMessageChannel.EMAIL
    draft.sent_at = timezone.now()
    draft.save(update_fields=["final_body_text", "channel", "sent_at"])

    return outbound


def send_guest_channex_image(
    *,
    reservation: Reservation,
    draft: GuestMessageDraft,
    uploaded_file,
    caption: str = "",
) -> ChannexMessage:
    """Send image via Channex Booking.com / Airbnb / Expedia messages API."""
    if not _booking_channel_available(reservation):
        raise ValueError("booking_channel_unavailable")

    integration = get_active_channex_integration(reservation.tenant.slug)
    if integration is None:
        raise ValueError("channex_not_configured")

    file_bytes = uploaded_file.read()
    uploaded_file.seek(0)
    if not file_bytes:
        raise ValueError("empty_file")

    mime_type = getattr(uploaded_file, "content_type", None) or mimetypes.guess_type(
        getattr(uploaded_file, "name", "") or ""
    )[0] or "image/jpeg"
    if not mime_type.startswith("image/"):
        raise ValueError("unsupported_media_type")

    filename = getattr(uploaded_file, "name", None) or "image.jpg"
    body_text = (caption or "").strip() or _OUTBOUND_IMAGE_BODY

    try:
        row = send_image_for_reservation(
            integration,
            reservation,
            file_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
            caption=(caption or "").strip(),
        )
    except ChannexBookingIngestError as exc:
        raise ValueError(str(exc)) from exc

    now = timezone.now()
    draft.final_body_text = body_text
    draft.channel = GuestMessageChannel.BOOKING
    draft.sent_at = now
    draft.save(update_fields=["final_body_text", "channel", "sent_at"])

    return row


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
