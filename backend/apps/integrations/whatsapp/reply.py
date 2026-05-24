from __future__ import annotations

from apps.communications.guest_email import _language_for_reservation
from apps.integrations.models import IntegrationConfig
from apps.reservations.models import Reservation


def _language_for_tenant(integration_row: IntegrationConfig) -> str:
    lang = (integration_row.tenant.default_language or "hr").strip()
    base = lang.split("-")[0].lower() or "hr"
    if base not in ("hr", "en"):
        return "en"
    return base


def build_greeting(
    *,
    integration_row: IntegrationConfig,
    reservation: Reservation | None,
    profile_name: str = "",
) -> str:
    if reservation is not None:
        language = _language_for_reservation(reservation)
        name = (reservation.booker_name or profile_name or "").strip() or (
            "gost" if language == "hr" else "guest"
        )
        if language == "hr":
            return (
                f"Bok {name}! Vidim rezervaciju {reservation.booking_code} "
                f"({reservation.check_in:%d.%m.%Y}–{reservation.check_out:%d.%m.%Y}) "
                f"u {reservation.property.name}. Kako vam mogu pomoći?"
            )
        return (
            f"Hi {name}! I see reservation {reservation.booking_code} "
            f"({reservation.check_in:%Y-%m-%d}–{reservation.check_out:%Y-%m-%d}) "
            f"at {reservation.property.name}. How can I help you?"
        )

    language = _language_for_tenant(integration_row)
    name = (profile_name or "").strip()
    if language == "hr":
        if name:
            return (
                f"Bok {name}! Ne mogu pronaći aktivnu rezervaciju za ovaj broj. "
                "Molimo pošaljite booking kod ili ime s kojim ste rezervirali."
            )
        return (
            "Bok! Ne mogu pronaći aktivnu rezervaciju za ovaj broj. "
            "Molimo pošaljite booking kod ili ime s kojim ste rezervirali."
        )
    if name:
        return (
            f"Hi {name}! I could not find an active reservation for this number. "
            "Please send your booking code or the name used for the reservation."
        )
    return (
        "Hi! I could not find an active reservation for this number. "
        "Please send your booking code or the name used for the reservation."
    )
