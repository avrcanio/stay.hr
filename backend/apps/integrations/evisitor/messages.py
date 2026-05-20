"""Parse and format eVisitor API user-facing messages."""

from __future__ import annotations

import re

_UUID_RE = re.compile(
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    re.IGNORECASE,
)


def format_evisitor_user_message(raw: str) -> str:
    """
    Turn eVisitor templated UserMessage into readable Croatian text.

    Example input:
      [[[Osoba %0 %1 je već prijavljena... %3|||Lauriane|||Saulnier|||20.5.2026.|||uuid]]]
    """
    text = (raw or "").strip()
    if not text:
        return ""

    if "|||" in text and ("[[[" in text or "%0" in text):
        parts = text.split("|||")
        # Drop template prefix before first placeholder value
        values = [p.strip().rstrip("]]]").strip() for p in parts[1:] if p.strip()]
        if len(values) >= 4:
            first, last, stay_date, reg_id = values[0], values[1], values[2], values[3]
            return (
                f"Osoba {first} {last} je već prijavljena na datum {stay_date} "
                f"te nije odjavljena. ID postojeće prijave: {reg_id}"
            )
        if values:
            return " ".join(values)

    # Strip Rhetos template wrappers if present
    text = text.removeprefix("[[[").removesuffix("]]]").strip()
    return text


def parse_existing_registration_id(user_message: str) -> str | None:
    """Extract existing eVisitor registration UUID from 'već prijavljena' errors."""
    formatted = format_evisitor_user_message(user_message)
    haystack = f"{user_message}\n{formatted}".lower()
    if "već prijavljena" not in haystack:
        return None

    if "|||" in user_message:
        parts = user_message.split("|||")
        for part in reversed(parts):
            candidate = part.strip().rstrip("]]]").strip()
            if _UUID_RE.fullmatch(candidate):
                return candidate.lower()

    matches = _UUID_RE.findall(user_message)
    if matches:
        return matches[-1].lower()
    return None
