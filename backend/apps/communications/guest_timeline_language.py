"""Walk guest timeline for detectable inbound text."""

from __future__ import annotations

import re
from datetime import datetime

from django.utils.dateparse import parse_datetime

from apps.communications.guest_message_timeline import timeline_for_reservation
from apps.reservations.models import Reservation

_DENYLIST = frozenset({"ok", "thanks", "grazie", "thx", "ty", "👍", "👌", "✅"})
_EMOJI_ONLY = re.compile(
    r"^[\s\U0001F300-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]+$"
)


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def is_detectable_inbound_text(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if lowered in _DENYLIST:
        return False
    if _EMOJI_ONLY.match(stripped):
        return False
    return len(stripped) >= 10 or _word_count(stripped) >= 3


def find_detectable_inbound_text(
    reservation: Reservation,
) -> tuple[str, datetime, str] | None:
    """
    Walk timeline newest-first; return (text, received_at, channel) for the
    latest inbound message with enough text for detection.
    """
    timeline = timeline_for_reservation(reservation)
    for item in reversed(timeline):
        if item.get("direction") != "inbound":
            continue
        body = (item.get("body_text") or "").strip()
        if not is_detectable_inbound_text(body):
            continue
        created_at = parse_datetime(item.get("created_at") or "")
        if created_at is None:
            continue
        channel = (item.get("channel") or "").strip()
        return body, created_at, channel
    return None
