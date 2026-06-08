"""Booker / guest phone normalization and validation."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError

BOOKER_PHONE_PATTERN = re.compile(r"^\+[0-9]{6,15}$")


def normalize_booker_phone(phone: str) -> str:
    """Strip invalid chars; fix common ± typo to leading +."""
    raw = (phone or "").strip()
    if not raw:
        return ""

    raw = raw.replace("±", "+").replace(" ", "")
    out: list[str] = []
    for char in raw:
        if char.isdigit():
            out.append(char)
        elif char == "+" and not out:
            out.append("+")
    return "".join(out)


def validate_booker_phone(phone: str) -> str:
    """Return normalized phone or raise ValidationError. Empty string allowed."""
    normalized = normalize_booker_phone(phone)
    if not normalized:
        return ""
    if not BOOKER_PHONE_PATTERN.match(normalized):
        raise ValidationError(
            "Telefon mora počinjati s + i sadržavati samo brojke (npr. +385977402538).",
            code="invalid_booker_phone",
        )
    return normalized
