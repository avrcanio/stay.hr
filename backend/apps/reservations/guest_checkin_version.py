"""Debounced CHECKIN version bumps during guest web check-in autosave."""

from __future__ import annotations

from django.core.cache import cache

from apps.reservations.models import ReservationVersionScope
from apps.reservations.reservation_version import touch_reservation_version

_DEBOUNCE_SECONDS = 5
_CACHE_KEY_PREFIX = "guest_checkin_version_debounce:"


def maybe_touch_checkin_version_debounced(reservation_id: int) -> None:
    """Rate-limit CHECKIN version bumps to once per reservation every 5 seconds."""
    key = f"{_CACHE_KEY_PREFIX}{reservation_id}"
    if not cache.add(key, 1, timeout=_DEBOUNCE_SECONDS):
        return
    touch_reservation_version(
        reservation_id,
        ReservationVersionScope.CHECKIN,
        reason="guest_checkin_autosave_debounced",
    )
