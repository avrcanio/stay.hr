from __future__ import annotations


def normalize_phone(phone: str) -> str:
    """Return digits-only phone number."""
    return "".join(char for char in (phone or "") if char.isdigit())


def phones_match(stored: str, wa_id: str) -> bool:
    norm_stored = normalize_phone(stored)
    norm_wa = normalize_phone(wa_id)
    if not norm_stored or not norm_wa:
        return False
    if norm_stored == norm_wa:
        return True
    if len(norm_stored) >= 9 and len(norm_wa) >= 9:
        return norm_stored[-9:] == norm_wa[-9:]
    return False
