"""Supported UI languages shared by booking, reception, and staff profiles."""

SUPPORTED_LANGUAGES = ["hr", "en", "es", "fr", "de", "it"]

DEFAULT_LANGUAGE = "hr"

LANGUAGE_CHOICES = [(code, code) for code in SUPPORTED_LANGUAGES]


def normalize_language(value: str | None, *, fallback: str = DEFAULT_LANGUAGE) -> str:
    if value and value in SUPPORTED_LANGUAGES:
        return value
    return fallback
