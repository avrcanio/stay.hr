"""On-demand guest message translation with server-side cache."""

from __future__ import annotations

from dataclasses import dataclass

from apps.ai.translate import translation_available, translate_text
from apps.api.language import normalize_app_language
from apps.communications.guest_message_timeline import (
    CHANNEX_ID_OFFSET,
    INBOUND_ID_OFFSET,
    WA_ID_OFFSET,
    whatsapp_display_body,
)
from apps.communications.models import (
    GuestInboundMessage,
    GuestMessageTranslation,
    GuestMessageTranslationSource,
    GuestOutboundMessage,
)
from apps.integrations.models import ChannexMessage, WhatsAppMessage
from apps.reservations.models import Reservation


class GuestMessageTranslateError(Exception):
    pass


@dataclass(frozen=True)
class ResolvedTimelineMessage:
    timeline_id: int
    message_source: str
    source_id: int
    body_text: str


def resolve_timeline_message(
    reservation: Reservation,
    timeline_id: int,
) -> ResolvedTimelineMessage:
    if timeline_id >= INBOUND_ID_OFFSET:
        source_id = timeline_id - INBOUND_ID_OFFSET
        row = GuestInboundMessage.objects.filter(
            tenant_id=reservation.tenant_id,
            reservation=reservation,
            pk=source_id,
        ).first()
        if row is None:
            raise GuestMessageTranslateError("Message not found.")
        return ResolvedTimelineMessage(
            timeline_id=timeline_id,
            message_source=GuestMessageTranslationSource.INBOUND,
            source_id=source_id,
            body_text=(row.body_text or "").strip(),
        )

    if timeline_id >= CHANNEX_ID_OFFSET:
        source_id = timeline_id - CHANNEX_ID_OFFSET
        row = ChannexMessage.objects.filter(
            tenant_id=reservation.tenant_id,
            reservation=reservation,
            pk=source_id,
        ).first()
        if row is None:
            raise GuestMessageTranslateError("Message not found.")
        body = (row.body or "").strip()
        return ResolvedTimelineMessage(
            timeline_id=timeline_id,
            message_source=GuestMessageTranslationSource.BOOKING,
            source_id=source_id,
            body_text=body,
        )

    if timeline_id >= WA_ID_OFFSET:
        source_id = timeline_id - WA_ID_OFFSET
        row = WhatsAppMessage.objects.filter(
            tenant_id=reservation.tenant_id,
            reservation=reservation,
            pk=source_id,
        ).first()
        if row is None:
            raise GuestMessageTranslateError("Message not found.")
        return ResolvedTimelineMessage(
            timeline_id=timeline_id,
            message_source=GuestMessageTranslationSource.WHATSAPP,
            source_id=source_id,
            body_text=whatsapp_display_body(row),
        )

    row = GuestOutboundMessage.objects.filter(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        pk=timeline_id,
    ).first()
    if row is None:
        raise GuestMessageTranslateError("Message not found.")
    return ResolvedTimelineMessage(
        timeline_id=timeline_id,
        message_source=GuestMessageTranslationSource.OUTBOUND,
        source_id=row.pk,
        body_text=(row.body_text or "").strip(),
    )


def translate_guest_message(
    *,
    reservation: Reservation,
    timeline_id: int,
    target_lang: str,
) -> dict:
    resolved = resolve_timeline_message(reservation, timeline_id)
    original = resolved.body_text
    lang = normalize_app_language(target_lang)

    if not original:
        return {
            "timeline_id": timeline_id,
            "original": original,
            "translated": original,
            "target_lang": lang,
            "is_translated": False,
            "from_cache": False,
        }

    cached = GuestMessageTranslation.objects.filter(
        tenant_id=reservation.tenant_id,
        message_source=resolved.message_source,
        source_id=resolved.source_id,
        target_lang=lang,
    ).first()
    if cached is not None and (cached.translated_text or "").strip():
        translated = cached.translated_text.strip()
        return {
            "timeline_id": timeline_id,
            "original": original,
            "translated": translated,
            "target_lang": lang,
            "is_translated": translated != original,
            "from_cache": True,
        }

    if not translation_available():
        return {
            "timeline_id": timeline_id,
            "original": original,
            "translated": original,
            "target_lang": lang,
            "is_translated": False,
            "from_cache": False,
        }

    translated = translate_text(original, lang)
    is_translated = translated.strip() != original.strip()
    if translated.strip():
        GuestMessageTranslation.objects.update_or_create(
            tenant_id=reservation.tenant_id,
            message_source=resolved.message_source,
            source_id=resolved.source_id,
            target_lang=lang,
            defaults={"translated_text": translated.strip()},
        )

    return {
        "timeline_id": timeline_id,
        "original": original,
        "translated": translated,
        "target_lang": lang,
        "is_translated": is_translated,
        "from_cache": False,
    }
