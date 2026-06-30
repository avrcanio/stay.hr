"""Single entry point for guest reply language resolution."""

from __future__ import annotations

from datetime import datetime

from apps.communications.conversation_language_store import load as load_conversation_language
from apps.communications.guest_language_constants import (
    CANONICAL_LANGUAGE_DEFAULT,
    normalize_iso639_1,
)
from apps.communications.guest_language_context import GuestLanguageContext, LanguageMode
from apps.communications.guest_language_policy import choose, detect_from_text
from apps.communications.guest_timeline_language import find_detectable_inbound_text
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.reservations.nationality_display import (
    normalize_country_iso2,
    reservation_nationality_iso2,
)


def canonical_language_for_property(property: Property) -> str:
    guest_info = property.guest_info or {}
    return normalize_iso639_1(
        guest_info.get("canonical_language")
        or property.language
        or property.tenant.default_language
        or CANONICAL_LANGUAGE_DEFAULT
    ) or CANONICAL_LANGUAGE_DEFAULT


class GuestLanguageResolver:
    @staticmethod
    def resolve(
        reservation: Reservation,
        *,
        mode: LanguageMode,
        override: str | None = None,
        reply_language: str | None = None,
        message_text: str = "",
    ) -> GuestLanguageContext:
        conversation = load_conversation_language(reservation)

        message_detection = None
        message_received_at: datetime | None = None
        message_channel = ""

        text = (message_text or "").strip()
        if text:
            message_detection = detect_from_text(text)
        elif mode == LanguageMode.REACTIVE:
            timeline_hit = find_detectable_inbound_text(reservation)
            if timeline_hit is not None:
                text, message_received_at, message_channel = timeline_hit
                message_detection = detect_from_text(text)

        country = normalize_country_iso2(reservation.booker_country)
        if not country:
            country = reservation_nationality_iso2(reservation) or ""

        prop = reservation.property
        tenant_default = normalize_iso639_1(getattr(reservation.tenant, "default_language", None))
        property_language = normalize_iso639_1(getattr(prop, "language", None))

        return choose(
            mode=mode,
            override=override,
            reply_language=reply_language,
            message_detection=message_detection,
            message_received_at=message_received_at,
            message_channel=message_channel,
            conversation=conversation,
            country_iso2=country,
            tenant_default=tenant_default,
            property_language=property_language,
        )
