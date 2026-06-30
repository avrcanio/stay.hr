"""Waive WhatsApp auto check-in and send the expired / reception check-in message."""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.communications.guest_compose import HINT_AUTOCHECKIN_WAIVED, render_autocheckin_waived_message
from apps.communications.guest_language_context import LanguageMode
from apps.communications.guest_language_resolver import GuestLanguageResolver
from apps.communications.guest_message_send import send_guest_message
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
)
from apps.integrations.whatsapp.apply_reply import waive_whatsapp_autocheckin
from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)


def send_autocheckin_waived_whatsapp(
    reservation: Reservation,
    *,
    api_application=None,
) -> dict:
    """Mark auto check-in waived and send reception check-in instructions (no entrance image)."""
    waive_whatsapp_autocheckin(reservation)
    reservation.refresh_from_db()

    body = render_autocheckin_waived_message(reservation)
    ctx = GuestLanguageResolver.resolve(reservation, mode=LanguageMode.PROACTIVE)
    lang = ctx.language

    draft = GuestMessageDraft.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        intent=GuestMessageIntent.CHECKIN,
        hint=HINT_AUTOCHECKIN_WAIVED,
        language=lang,
        language_source=ctx.source.value,
        language_reason=(ctx.reason or "")[:255],
        llm_body_text=body,
        final_body_text="",
        channel=GuestMessageChannel.WHATSAPP,
        api_application=api_application,
    )

    try:
        outbound = send_guest_message(
            reservation=reservation,
            draft=draft,
            channel=GuestMessageChannel.WHATSAPP,
            body_text=body,
            api_application=api_application,
        )
    except ValueError as exc:
        logger.warning(
            "autocheckin waived WhatsApp failed reservation_id=%s: %s",
            reservation.pk,
            exc,
        )
        return {"status": "send_failed", "detail": str(exc), "reservation_id": reservation.pk}

    draft.sent_at = timezone.now()
    draft.save(update_fields=["sent_at"])

    return {
        "status": "sent",
        "reservation_id": reservation.pk,
        "outbound_id": outbound.pk,
        "waived_at": reservation.whatsapp_autocheckin_waived_at,
    }
