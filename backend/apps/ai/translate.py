"""OpenAI text translation for reception UI (guest reviews, etc.)."""

from __future__ import annotations

import logging

from apps.ai.provider import GuestComposeError, complete_chat, llm_configured
from apps.api.language import SUPPORTED_APP_LANGS, normalize_app_language

logger = logging.getLogger(__name__)

LANG_NAMES: dict[str, str] = {
    "hr": "Croatian",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
}


class TranslationError(Exception):
    """Translation failed or LLM is not configured."""


def translation_available() -> bool:
    return llm_configured()


def translate_text(text: str, target_lang: str) -> str:
    """Translate text to target_lang; return original on failure or empty input."""
    cleaned = (text or "").strip()
    if not cleaned:
        return text

    lang = normalize_app_language(target_lang)
    if lang not in SUPPORTED_APP_LANGS:
        lang = "en"

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
