"""OpenAI text translation for reception UI (guest reviews, etc.)."""

from __future__ import annotations

import logging

from apps.ai.provider import GuestComposeError, complete_chat, llm_configured
from apps.api.language import normalize_app_language
from apps.communications.guest_language_constants import TRANSLATION_LANGS

logger = logging.getLogger(__name__)

LANG_NAMES: dict[str, str] = {
    "hr": "Croatian",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "sk": "Slovak",
    "pl": "Polish",
    "ro": "Romanian",
}


class TranslationError(Exception):
    """Translation failed or LLM is not configured."""


def translation_available() -> bool:
    return llm_configured()


def _normalize_target_lang(raw: str) -> str:
    base = (raw or "").split("-")[0].strip().lower()
    if base in TRANSLATION_LANGS:
        return base
    return normalize_app_language(raw)


def translate_text(text: str, target_lang: str) -> str:
    """Translate text to target_lang; return original on failure or empty input."""
    cleaned = (text or "").strip()
    if not cleaned:
        return text

    lang = _normalize_target_lang(target_lang)

    if not llm_configured():
        return text

    lang_name = LANG_NAMES.get(lang, lang)
    system = (
        f"You translate hotel guest review text into {lang_name}. "
        "If the text is already in that language, return it unchanged. "
        "Preserve tone and meaning. Return only the translated text, without quotes."
    )
    try:
        translated = complete_chat(system, cleaned)
    except GuestComposeError as exc:
        logger.warning("review translation failed: %s", exc)
        return text

    result = (translated or "").strip()
    return result or text
