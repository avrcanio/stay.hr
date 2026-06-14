"""Guest message compose language selection from country / API override."""

from __future__ import annotations

from apps.communications.guest_email import _language_for_reservation
from apps.reservations.models import Reservation
from apps.reservations.nationality_display import (
    normalize_country_iso2,
    reservation_nationality_iso2,
)

SUPPORTED_COMPOSE_LANGS = frozenset({"hr", "en", "de", "es", "fr", "sk"})

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


def detect_message_language(text: str) -> str:
    """Best-effort language from inbound guest message text."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return "en"

    sk_markers = (
        "ľ",
        "ô",
        "ŕ",
        "veľk",
        "izba",
        "záchod",
        "ďakuj",
        "špinav",
        "kúpeľ",
        "ste ",
        "sme ",
        "prie",
    )
    if any(marker in lowered for marker in sk_markers):
        return "sk"

    de_markers = ("ß", "schön", "danke", "zimmer", "übernacht", "gäste", "spät", "ankunft", "können", "spaeter")
    if any(marker in lowered for marker in de_markers):
        return "de"

    hr_markers = (
        "hvala",
        "soba",
        "boravak",
        "gost",
        "žao",
        "čist",
        "dolaz",
        "doći",
        "možemo",
        "večer",
        "vecer",
        "kasnij",
    )
    if any(marker in lowered for marker in hr_markers):
        return "hr"

    es_markers = ("gracias", "habitación", "llegada", "tarde", "noche", "podemos")
    if any(marker in lowered for marker in es_markers):
        return "es"

    fr_markers = ("merci", "chambre", "arrivée", "arrivee", "soir", "tard", "pouvons")
    if any(marker in lowered for marker in fr_markers):
        return "fr"

    it_markers = ("grazie", "camera", "arrivo", "sera", "tardi", "possiamo")
    if any(marker in lowered for marker in it_markers):
        return "it"

    return "en"


def resolve_arrival_reply_language(
    reservation: Reservation,
    *,
    llm_language: str | None = None,
    message_text: str = "",
) -> str:
    """Priority: LLM reply_language → detect from message → reservation compose language."""
    if llm_language:
        base = llm_language.split("-")[0].lower()
        if base in SUPPORTED_COMPOSE_LANGS:
            return base

    detected = detect_message_language(message_text)
    if detected in SUPPORTED_COMPOSE_LANGS:
        return detected

    return compose_language_for_reservation(reservation)
