from __future__ import annotations

from typing import Any

from apps.communications.guest_compose import build_compose_context
from apps.communications.guest_language_context import LanguageMode
from apps.communications.guest_language_resolver import GuestLanguageResolver
from apps.communications.guest_email import _email_context
from apps.reservations.models import Reservation

DEFAULT_WELCOME_HEADER_IMAGE = "https://stay.hr/static/whatsapp-header.png"

DEFAULT_WELCOME_TEMPLATES: dict[str, str] = {
    "hr": "stay_welcome_hr",
    "en": "stay_welcome_en",
    "de": "stay_welcome_de",
    "es": "stay_welcome_es",
    "fr": "stay_welcome_fr",
    "it": "stay_welcome_it",
    "pl": "stay_welcome_pl",
    "sk": "stay_welcome_sk",
    "nl": "stay_welcome_nl",
    "lt": "stay_welcome_lt",
    "ua": "stay_welcome_ua",
    "hu": "stay_welcome_hu",
    "cs": "stay_welcome_cs",
    "ro": "stay_welcome_ro",
}


def welcome_header_image_url(config: dict[str, Any]) -> str:
    templates_cfg = config.get("whatsapp_templates") or {}
    header = str(templates_cfg.get("header_image_url") or "").strip()
    return header or DEFAULT_WELCOME_HEADER_IMAGE


def welcome_template_name(*, config: dict[str, Any], lang: str) -> str:
    templates_cfg = config.get("whatsapp_templates") or {}
    welcome_map = templates_cfg.get("welcome") or {}
    if isinstance(welcome_map, dict):
        name = str(welcome_map.get(lang) or welcome_map.get("en") or "").strip()
        if name:
            return name
    # ISO 639-1 Ukrainian is "uk"; internal/country key is "ua".
    if lang == "uk":
        lang = "ua"
    return DEFAULT_WELCOME_TEMPLATES.get(lang) or DEFAULT_WELCOME_TEMPLATES["en"]


# Guest/country language key → Meta template language code (ISO 639-1 / WhatsApp).
# UA (Ukraine) uses internal key "ua"; Meta expects "uk" for Ukrainian text.
WELCOME_META_LANGUAGE_CODES: dict[str, str] = {
    "ua": "uk",
}


def welcome_meta_language_code(guest_lang: str) -> str:
    if guest_lang == "uk":
        guest_lang = "ua"
    return WELCOME_META_LANGUAGE_CODES.get(guest_lang, guest_lang)


def _first_name(reservation: Reservation) -> str:
    booker = (reservation.booker_name or "").strip()
    if booker:
        return booker.split()[0]
    primary = reservation.guests.filter(is_primary=True).first()
    if primary and (primary.first_name or "").strip():
        return primary.first_name.strip()
    return booker or "Guest"


def build_welcome_template_parameters(reservation: Reservation) -> tuple[str, list[str]]:
    """Return (language_code, five positional body parameters for stay_welcome_* templates)."""
    ctx = GuestLanguageResolver.resolve(reservation, mode=LanguageMode.PROACTIVE)
    lang = ctx.language
    ctx = build_compose_context(reservation, language=lang)
    email_ctx = _email_context(reservation)

    params = [
        _first_name(reservation),
        ctx["booking_code"] or str(reservation.pk),
        ctx["property_name"],
        email_ctx["check_in_display"],
        email_ctx["check_out_display"],
    ]
    return lang, params
