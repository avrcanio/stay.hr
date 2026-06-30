"""Deprecated — use GuestLanguageResolver. Thin re-exports for one release."""

from __future__ import annotations

from apps.communications.guest_language_constants import TEMPLATE_LANGS as SUPPORTED_COMPOSE_LANGS
from apps.communications.guest_language_context import LanguageMode
from apps.communications.guest_language_policy import language_from_country
from apps.communications.guest_language_resolver import GuestLanguageResolver
from apps.communications.language_detection import detect


def detect_message_language(text: str) -> str:
    result = detect(text)
    if result.language == "unknown":
        return "en"
    return result.language
from apps.reservations.models import Reservation


def compose_language_for_reservation(
    reservation: Reservation,
    override: str | None = None,
) -> str:
    ctx = GuestLanguageResolver.resolve(
        reservation,
        mode=LanguageMode.PROACTIVE,
        override=override,
    )
    return ctx.language


def resolve_arrival_reply_language(
    reservation: Reservation,
    *,
    llm_language: str | None = None,
    message_text: str = "",
) -> str:
    ctx = GuestLanguageResolver.resolve(
        reservation,
        mode=LanguageMode.REACTIVE,
        reply_language=llm_language,
        message_text=message_text,
    )
    return ctx.language


def resolve_parking_reply_language(
    reservation: Reservation,
    *,
    llm_language: str | None = None,
    message_text: str = "",
) -> str:
    return resolve_arrival_reply_language(
        reservation,
        llm_language=llm_language,
        message_text=message_text,
    )


__all__ = [
    "SUPPORTED_COMPOSE_LANGS",
    "compose_language_for_reservation",
    "detect_message_language",
    "language_from_country",
    "resolve_arrival_reply_language",
    "resolve_parking_reply_language",
]
