"""Guest message compose language selection from country / API override."""

from __future__ import annotations

from apps.communications.guest_email import _language_for_reservation
from apps.reservations.models import Reservation
from apps.reservations.nationality_display import (
    normalize_country_iso2,
    reservation_nationality_iso2,
)

SUPPORTED_COMPOSE_LANGS = frozenset({"hr", "en", "de", "es", "fr"})

HR_COUNTRIES = frozenset({"HR", "RS", "BA", "ME", "SI", "MK"})
DE_COUNTRIES = frozenset({"DE", "AT", "CH", "LI"})
ES_COUNTRIES = frozenset(
    {
        "ES",
        "MX",
        "AR",
        "CO",
        "CL",
        "PE",
        "VE",
        "EC",
        "UY",
        "PY",
        "BO",
        "CR",
        "PA",
        "DO",
        "GT",
        "HN",
        "NI",
        "SV",
        "CU",
        "PR",
    }
)
FR_COUNTRIES = frozenset({"FR", "MC", "LU"})


def language_from_country(iso2: str) -> str:
    """Map ISO2 country code to compose template language."""
    code = normalize_country_iso2(iso2)
    if not code:
        return "en"
    if code in HR_COUNTRIES:
        return "hr"
    if code in DE_COUNTRIES:
        return "de"
    if code in ES_COUNTRIES:
        return "es"
    if code in FR_COUNTRIES:
        return "fr"
    return "en"


def compose_language_for_reservation(
    reservation: Reservation,
    override: str | None = None,
) -> str:
    """
    Resolve template language for guest compose.

    Priority: API override → booker_country → guest nationality → property default → en.
    """
    if override:
        base = override.split("-")[0].lower()
        if base in SUPPORTED_COMPOSE_LANGS:
            return base

    country = normalize_country_iso2(reservation.booker_country)
    if not country:
        country = reservation_nationality_iso2(reservation)
    if country:
        return language_from_country(country)

    prop_lang = _language_for_reservation(reservation)
    if prop_lang in SUPPORTED_COMPOSE_LANGS:
        return prop_lang
    return "en"
