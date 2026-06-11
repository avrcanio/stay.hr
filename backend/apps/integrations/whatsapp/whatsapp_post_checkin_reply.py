"""Auto WhatsApp reply after document check-in is complete (parking / arrival)."""

from __future__ import annotations

import re

from apps.communications.guest_compose import (
    HINT_AUTOCHECKIN_ARRIVAL_THANKS,
    HINT_POST_CHECKIN_AUTO_REPLY,
    render_arrival_thanks_message,
    render_entrance_image_caption,
    render_post_checkin_guest_reply,
)
from apps.communications.guest_message_send import (
    send_guest_message,
    send_whatsapp_entrance_image_from_asset,
)
from apps.communications.models import GuestMessageChannel, GuestMessageDraft, GuestMessageIntent
from apps.core.timezone import property_local_now
from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.reservations.models import Reservation

_ARRIVAL_PATTERN = re.compile(
    r"\b(arrive|arrival|arriving|dolaz\w*|dolaska|stignu|check.?in|reception|recepction|"
    r"evening|večer|vecer|noc|night|pm|p\.m\.|\d{1,2}\s*(?:pm|h))\b",
    re.IGNORECASE,
)
_PARKING_PATTERN = re.compile(
    r"\b(parking|parkir|parkiranje|parkplatz|aparcamiento|stationnement|park|"
    r"leave my car|where.*car|car space)\b",
    re.IGNORECASE,
)
_EVENING_PATTERN = re.compile(
    r"\b(evening|večer|vecer|noc|night|pm|p\.m\.|\d{1,2}\s*(?:pm|h))\b",
    re.IGNORECASE,
)


def guest_message_mentions_arrival(action_text: str) -> bool:
    text = (action_text or "").strip()
    if not text:
        return False
    return bool(_ARRIVAL_PATTERN.search(text))


def guest_message_needs_post_checkin_reply(action_text: str) -> bool:
    text = (action_text or "").strip()
    if not text:
        return False
    return bool(_ARRIVAL_PATTERN.search(text) or _PARKING_PATTERN.search(text))


def parse_post_checkin_message_hints(
    action_text: str,
    *,
    reservation: Reservation,
) -> dict[str, bool]:
    text = (action_text or "").strip()
    mentions_arrival = bool(_ARRIVAL_PATTERN.search(text))
    mentions_parking = bool(_PARKING_PATTERN.search(text))
    evening_welcome = False
    if reservation.check_in == property_local_now(reservation.property).date():
        evening_welcome = bool(_EVENING_PATTERN.search(text))
    return {
        "mentions_arrival": mentions_arrival,
        "mentions_parking": mentions_parking,
        "evening_welcome": evening_welcome,
    }


def arrival_thanks_sent_today(reservation: Reservation) -> bool:
    now = property_local_now(reservation.property)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return GuestMessageDraft.objects.filter(
        reservation=reservation,
        hint=HINT_AUTOCHECKIN_ARRIVAL_THANKS,
        sent_at__gte=start_of_day,
    ).exists()


def post_checkin_auto_reply_already_sent_today(reservation: Reservation) -> bool:
    now = property_local_now(reservation.property)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return GuestMessageDraft.objects.filter(
        reservation=reservation,
        hint=HINT_POST_CHECKIN_AUTO_REPLY,
        sent_at__gte=start_of_day,
    ).exists()


def send_post_checkin_whatsapp_auto_reply(
    *,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    row: WhatsAppMessage,
    reservation: Reservation,
    mentions_arrival: bool,
    mentions_parking: bool,
    evening_welcome: bool,
) -> dict:
    del integration_row, runtime  # send_guest_message resolves integration from tenant

    body = render_post_checkin_guest_reply(
        reservation,
        mentions_arrival=mentions_arrival,
        mentions_parking=mentions_parking,
        evening_welcome=evening_welcome,
    )
    lang = (reservation.property.tenant.default_language or "en")[:2]

    text_draft = GuestMessageDraft.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        intent=GuestMessageIntent.REPLY,
        hint=HINT_POST_CHECKIN_AUTO_REPLY,
        llm_body_text=body,
        final_body_text=body,
        language=lang,
        channel=GuestMessageChannel.WHATSAPP,
    )

    try:
        send_guest_message(
            reservation=reservation,
            draft=text_draft,
            channel=GuestMessageChannel.WHATSAPP,
            body_text=body,
            api_application=None,
        )
    except ValueError as exc:
        return {"status": "send_failed", "detail": str(exc)}

    caption = render_entrance_image_caption(reservation)
    image_draft = GuestMessageDraft.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        intent=GuestMessageIntent.REPLY,
        hint=HINT_POST_CHECKIN_AUTO_REPLY,
        llm_body_text=caption,
        final_body_text=caption,
        language=lang,
        channel=GuestMessageChannel.WHATSAPP,
    )

    try:
        send_whatsapp_entrance_image_from_asset(
            reservation=reservation,
            draft=image_draft,
            caption=caption,
            api_application=None,
        )
    except ValueError as exc:
        logger_msg = str(exc)
        return {
            "status": "post_checkin_reply_sent",
            "reason": "entrance_image_failed",
            "detail": logger_msg,
        }

    return {"status": "post_checkin_reply_sent"}


def send_arrival_thanks_only(
    *,
    row: WhatsAppMessage,
    reservation: Reservation,
) -> dict:
    """Short arrival-time thanks for waived auto check-in (no parking / entrance)."""
    del row  # send_guest_message resolves phone from reservation

    body = render_arrival_thanks_message(reservation)
    lang = (reservation.property.tenant.default_language or "en")[:2]

    draft = GuestMessageDraft.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        intent=GuestMessageIntent.REPLY,
        hint=HINT_AUTOCHECKIN_ARRIVAL_THANKS,
        llm_body_text=body,
        final_body_text=body,
        language=lang,
        channel=GuestMessageChannel.WHATSAPP,
    )

    try:
        send_guest_message(
            reservation=reservation,
            draft=draft,
            channel=GuestMessageChannel.WHATSAPP,
            body_text=body,
            api_application=None,
        )
    except ValueError as exc:
        return {"status": "send_failed", "detail": str(exc)}

    return {"status": "arrival_thanks_sent"}
