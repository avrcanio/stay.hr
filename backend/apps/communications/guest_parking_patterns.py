"""Shared regex helpers for guest parking questions."""

from __future__ import annotations

import re

_PARKING_PATTERN = re.compile(
    r"\b(parking|parkir|parkiranje|parkplatz|aparcamiento|stationnement|park|"
    r"leave my car|where.*car|car space)\b",
    re.IGNORECASE,
)

_ARRIVAL_PATTERN = re.compile(
    r"\b(arrive|arrival|arriving|dolaz\w*|dolaska|stignu|check.?in|reception|recepction|"
    r"evening|večer|vecer|noc|night|pm|p\.m\.|\d{1,2}\s*(?:pm|h))\b",
    re.IGNORECASE,
)

_RESERVATION_PARKING_NOTES = re.compile(
    r"\b(parking|parkir\w*|free parking|besplatn\w*\s+parkir\w*)\b",
    re.IGNORECASE,
)


def guest_message_mentions_parking(text: str) -> bool:
    return bool(_PARKING_PATTERN.search((text or "").strip()))


def guest_message_mentions_arrival_for_parking_split(text: str) -> bool:
    """True when message also mentions arrival/time (defer to arrival handler)."""
    return bool(_ARRIVAL_PATTERN.search((text or "").strip()))


def classify_parking_only(text: str) -> bool:
    """Parking question without arrival/time context."""
    body = (text or "").strip()
    if not body:
        return False
    return guest_message_mentions_parking(body) and not guest_message_mentions_arrival_for_parking_split(
        body
    )


def reservation_notes_request_parking(notes: str) -> bool:
    return bool(_RESERVATION_PARKING_NOTES.search((notes or "").strip()))
