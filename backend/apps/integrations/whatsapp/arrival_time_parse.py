"""Parse guest/operator arrival time from WhatsApp free text."""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from apps.core.timezone import effective_guest_stated_arrival_at, effective_timezone, property_local_now
from apps.reservations.models import Reservation

_TIME_PAIR = re.compile(
    r"(?P<h1>\d{1,2})"
    r"(?:[:.](?P<m1>\d{2})|\s*h)?"
    r"\s*(?:\.\.\.|…|–|-|—|bis|to|do)\s*"
    r"(?P<h2>\d{1,2})"
    r"(?:[:.](?P<m2>\d{2})|\s*h)?",
    re.IGNORECASE,
)
_TIME_EXPLICIT = re.compile(
    r"(?<!\d)(?P<h>\d{1,2})[:.](?P<m>\d{2})(?!\d)",
)
_TIME_H_SUFFIX = re.compile(
    r"(?<!\d)(?P<h>\d{1,2})\s*h\b",
    re.IGNORECASE,
)
_TIME_HOUR_ONLY = re.compile(
    r"(?<!\d)(?P<h>\d{1,2})(?!\d(?:[:.]\d{2}|\s*h))",
)


def _property_tz(reservation: Reservation) -> ZoneInfo:
    return ZoneInfo(effective_timezone(property=reservation.property, tenant=reservation.tenant))


def _combine_on_check_in(reservation: Reservation, hour: int, minute: int) -> datetime:
    hour = max(0, min(hour, 23))
    minute = max(0, min(minute, 59))
    tz = _property_tz(reservation)
    return datetime.combine(reservation.check_in, time(hour, minute), tzinfo=tz)


def _parse_clock(hour: int, minute: int | None) -> tuple[int, int] | None:
    if hour < 0 or hour > 23:
        return None
    if minute is None:
        minute = 0
    if minute < 0 or minute > 59:
        return None
    return hour, minute


def _extract_times(text: str) -> list[tuple[int, int]]:
    normalized = (text or "").strip()
    if not normalized:
        return []

    pair = _TIME_PAIR.search(normalized)
    if pair:
        h1 = int(pair.group("h1"))
        m1 = int(pair.group("m1") or 0)
        h2 = int(pair.group("h2"))
        m2 = int(pair.group("m2") or 0)
        first = _parse_clock(h1, m1)
        second = _parse_clock(h2, m2)
        if first and second:
            return [first, second]

    for pattern in (_TIME_EXPLICIT, _TIME_H_SUFFIX, _TIME_HOUR_ONLY):
        match = pattern.search(normalized)
        if not match:
            continue
        parsed = _parse_clock(int(match.group("h")), int(match.group("m")) if "m" in match.groupdict() and match.group("m") else None)
        if parsed:
            return [parsed]
    return []


_RELATIVE_HOURS = re.compile(
    r"za\s+(?P<n>\d+)\s*sata",
    re.IGNORECASE,
)
_RELATIVE_MINUTE_RULES: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"za\s+sat\s+do\s+sat\s+i\s+pol", re.IGNORECASE), 90),
    (re.compile(r"za\s+sat\s+i\s+pol", re.IGNORECASE), 90),
    (re.compile(r"(?:za\s+)?sat\s+sat\s+i\s+pol", re.IGNORECASE), 90),
    (re.compile(r"in\s+an?\s+hour\s+and\s+a\s+half", re.IGNORECASE), 90),
    (re.compile(r"in\s+one\s+to\s+one\s+and\s+a\s+half\s+hours?", re.IGNORECASE), 90),
    (re.compile(r"za\s+pola?\s+sata", re.IGNORECASE), 30),
    (re.compile(r"in\s+half\s+an?\s+hour", re.IGNORECASE), 30),
    (re.compile(r"za\s+sat\b(?!\s+(?:do|i\s+pol))", re.IGNORECASE), 60),
    (re.compile(r"in\s+an?\s+hour\b", re.IGNORECASE), 60),
]


def _parse_relative_arrival_minutes(text: str) -> int | None:
    normalized = (text or "").strip()
    if not normalized:
        return None

    hours_match = _RELATIVE_HOURS.search(normalized)
    if hours_match:
        try:
            hours = int(hours_match.group("n"))
        except (TypeError, ValueError):
            return None
        if 1 <= hours <= 12:
            return hours * 60

    for pattern, minutes in _RELATIVE_MINUTE_RULES:
        if pattern.search(normalized):
            return minutes
    return None


def _check_in_earliest_at(reservation: Reservation) -> datetime:
    tz = _property_tz(reservation)
    return datetime.combine(
        reservation.check_in,
        reservation.property.check_in_time,
        tzinfo=tz,
    )


def _floor_to_check_in_earliest(reservation: Reservation, computed: datetime) -> datetime:
    tz = _property_tz(reservation)
    local = computed.astimezone(tz) if computed.tzinfo else computed.replace(tzinfo=tz)
    earliest = _check_in_earliest_at(reservation)
    if local < earliest:
        return earliest
    return local


def _parse_relative_arrival_at(
    text: str,
    reservation: Reservation,
    *,
    reference_at: datetime,
) -> datetime | None:
    minutes = _parse_relative_arrival_minutes(text)
    if minutes is None:
        return None

    tz = _property_tz(reservation)
    ref = reference_at.astimezone(tz) if reference_at.tzinfo else reference_at.replace(tzinfo=tz)
    if ref.date() != reservation.check_in:
        return None

    computed = ref + timedelta(minutes=minutes)
    return _floor_to_check_in_earliest(reservation, computed)


def parse_guest_stated_arrival(
    text: str,
    reservation: Reservation,
    *,
    reference_at: datetime | None = None,
) -> datetime | None:
    """Return arrival datetime on check-in date (absolute time or relative to reference_at)."""
    times = _extract_times(text)
    if times:
        hour, minute = times[-1]
        return _combine_on_check_in(reservation, hour, minute)

    ref = reference_at
    if ref is None:
        ref = property_local_now(reservation.property)
    return _parse_relative_arrival_at(text, reservation, reference_at=ref)


def parse_operator_confirmed_arrival_time(
    text: str,
    reservation: Reservation,
    *,
    reference_at: datetime | None = None,
) -> datetime | None:
    """Parse HH:MM (or H) from operator reply on check-in date."""
    return parse_guest_stated_arrival(text, reservation, reference_at=reference_at)


def format_guest_stated_arrival_for_operator(reservation: Reservation) -> str:
    """Human-readable guest plan for Toni prompt (property-local time)."""
    if reservation.guest_stated_arrival_text.strip():
        return reservation.guest_stated_arrival_text.strip()
    stated_at = effective_guest_stated_arrival_at(reservation)
    tz = _property_tz(reservation)
    local = stated_at.astimezone(tz)
    return local.strftime("%H:%M")
