"""Booking.com / OTA public review reply compliance rules."""

from __future__ import annotations

import re

BOOKING_COM_OTA = "BookingCom"

BOOKING_MAX_LEN = 500

NEGATIVE_KEYWORDS = frozenset(
    {
        "dirty",
        "filthy",
        "disgusting",
        "insect",
        "bug",
        "cockroach",
        "mold",
        "mould",
        "smell",
        "odor",
        "odour",
        "noise",
        "noisy",
        "rude",
        "unprofessional",
        "broken",
        "unsafe",
        "špinav",
        "prljav",
        "buka",
        "bucno",
        "insecte",
        "schmutzig",
        "lärm",
        "lärmbelastung",
    }
)

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
URL_RE = re.compile(
    r"(?:https?://|www\.|wa\.me/|booking\.com/)",
    re.IGNORECASE,
)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)",
)
BOOKING_CODE_RE = re.compile(r"(?<!\d)(\d{6,12})(?!\d)")


def _contains_contact_or_link(text: str) -> bool:
    lowered = (text or "").lower()
    if "@" in lowered and EMAIL_RE.search(text):
        return True
    if URL_RE.search(text):
        return True
    if PHONE_RE.search(text):
        return True
    return False


def _guest_name_in_text(text: str, guest_name: str) -> bool:
    name = (guest_name or "").strip()
    if len(name) < 2:
        return False
    pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
    return bool(pattern.search(text or ""))


def _negative_words_from_review(review_content: str) -> set[str]:
    words: set[str] = set()
    for token in re.findall(r"[A-Za-zÀ-ž]{5,}", review_content or ""):
        words.add(token.lower())
    return words


def _repeats_negative_review_language(text: str, review_content: str) -> bool:
    review_words = _negative_words_from_review(review_content)
    lowered = (text or "").lower()
    for keyword in NEGATIVE_KEYWORDS:
        if keyword in lowered and keyword in (review_content or "").lower():
            return True
    for word in review_words:
        if len(word) >= 6 and word in lowered:
            return True
    return False


def booking_compliant_fallback(lang: str) -> str:
    code = (lang or "en").split("-")[0].lower()
    templates = {
        "hr": (
            "Hvala vam na recenziji i što ste odabrali naš smještaj. "
            "Cijenimo vaše mišljenje i radimo na poboljšanjima. "
            "Nadamo se da ćemo vas ponovno ugostiti."
        ),
        "de": (
            "Vielen Dank für Ihre Bewertung und Ihren Aufenthalt bei uns. "
            "Ihr Feedback ist uns wichtig und hilft uns, unseren Service zu verbessern. "
            "Wir würden uns freuen, Sie wieder begrüßen zu dürfen."
        ),
        "sk": (
            "Ďakujeme za vašu recenziu a za pobyt u nás. "
            "Vašu spätnú väzbu si vážime a pracujeme na zlepšeniach. "
            "Tešíme sa na ďalšie privítanie."
        ),
        "es": (
            "Gracias por su reseña y por alojarse con nosotros. "
            "Valoramos sus comentarios y seguimos mejorando. "
            "Esperamos recibirle de nuevo."
        ),
        "fr": (
            "Merci pour votre avis et votre séjour chez nous. "
            "Nous apprécions vos commentaires et travaillons à nous améliorer. "
            "Au plaisir de vous accueillir à nouveau."
        ),
        "en": (
            "Thank you for your review and for staying with us. "
            "We appreciate your feedback and are always working to improve. "
            "We hope to welcome you again."
        ),
    }
    return templates.get(code, templates["en"])


def validate_review_reply(
    text: str,
    *,
    ota: str,
    guest_name: str = "",
    review_content: str = "",
) -> list[str]:
    """Return validation errors; empty list means the reply is acceptable."""
    body = (text or "").strip()
    errors: list[str] = []

    if not body:
        errors.append("Reply text is required.")
        return errors

    if ota == BOOKING_COM_OTA:
        if len(body) > BOOKING_MAX_LEN:
            errors.append(f"Reply must be at most {BOOKING_MAX_LEN} characters for Booking.com.")

        if _contains_contact_or_link(body):
            errors.append("Do not include email addresses, phone numbers, or links.")

        if BOOKING_CODE_RE.search(body):
            errors.append("Do not include booking or confirmation numbers.")

        if _guest_name_in_text(body, guest_name):
            errors.append("Do not address the guest by name.")

        if _repeats_negative_review_language(body, review_content):
            errors.append("Do not repeat explicit negative details from the review.")

    return errors


def hint_is_compliant(hint: str) -> bool:
    """Staff compose hints must not inject contact details or URLs."""
    return not _contains_contact_or_link(hint or "")
