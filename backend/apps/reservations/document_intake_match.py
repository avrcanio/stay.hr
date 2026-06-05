"""Match OCR persons to active reservations and guest slots."""

from __future__ import annotations

import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.reservations.booking_xls_import import (
    _find_guest_by_full_name,
    _guest_display_name,
    _normalize_guest_name_key,
)
from apps.reservations.guest_slots import is_unfilled_guest
from apps.reservations.models import Guest, Reservation

ZAGREB = ZoneInfo("Europe/Zagreb")
ACTIVE_STATUSES = frozenset(
    {
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
    }
)


def _person_full_name(person: dict) -> str:
    given = str(person.get("given_names") or "").strip()
    surnames = str(person.get("surnames") or "").strip()
    if given and surnames:
        return f"{given} {surnames}"
    return given or surnames


def _person_name_keys(person: dict) -> set[str]:
    keys: set[str] = set()
    full = _normalize_guest_name_key(_person_full_name(person))
    if full:
        keys.add(full)
    surnames = _normalize_guest_name_key(str(person.get("surnames") or ""))
    given = _normalize_guest_name_key(str(person.get("given_names") or ""))
    if surnames and given:
        keys.add(f"{given} {surnames}")
    if surnames:
        keys.add(surnames)
    return {k for k in keys if k}


def active_reservations_for_intake(tenant_id: int) -> list[Reservation]:
    today = timezone.now().astimezone(ZAGREB).date()
    window_start = today - timedelta(days=3)
    window_end = today + timedelta(days=14)
    qs = (
        Reservation.objects.filter(
            tenant_id=tenant_id,
            status__in=ACTIVE_STATUSES,
            check_in_date__lte=window_end,
            check_out_date__gte=window_start,
        )
        .prefetch_related("guests")
        .order_by("check_in_date", "id")
    )
    return list(qs)


def _guest_name_matches(guest: Guest, keys: set[str]) -> bool:
    display_key = _normalize_guest_name_key(_guest_display_name(guest))
    if display_key and display_key in keys:
        return True
    first_last = _normalize_guest_name_key(f"{guest.first_name} {guest.last_name}".strip())
    if first_last and first_last in keys:
        return True
    last_first = _normalize_guest_name_key(f"{guest.last_name} {guest.first_name}".strip())
    if last_first and last_first in keys:
        return True
    return False


def _fuzzy_guest_match(reservation: Reservation, keys: set[str]) -> Guest | None:
    for guest in reservation.guests.all():
        if _guest_name_matches(guest, keys):
            return guest
    return None


def _find_unfilled_slot(reservation: Reservation) -> Guest | None:
    for guest in reservation.guests.all():
        if is_unfilled_guest(guest):
            return guest
    return None


def match_persons_to_guests(
    *,
    tenant_id: int,
    persons: list[dict],
) -> list[dict]:
    """Return match suggestions per person index."""
    reservations = active_reservations_for_intake(tenant_id)
    results: list[dict] = []

    for idx, person in enumerate(persons):
        keys = _person_name_keys(person)
        full_name = _person_full_name(person)
        candidates: list[dict] = []

        for reservation in reservations:
            guest = None
            match_type = ""
            if keys:
                guest = _fuzzy_guest_match(reservation, keys)
                if guest:
                    match_type = "name"
            if guest is None:
                guest = _find_unfilled_slot(reservation)
                if guest and keys:
                    match_type = "unfilled_slot"

            if guest is None:
                continue

            candidates.append(
                {
                    "reservation_id": reservation.pk,
                    "guest_id": guest.pk,
                    "guest_name": _guest_display_name(guest),
                    "reservation_label": _reservation_label(reservation),
                    "match_type": match_type,
                    "check_in_date": reservation.check_in_date.isoformat(),
                }
            )

        confidence = _confidence_for_candidates(candidates, keys)
        auto_apply = confidence == "high" and len(candidates) == 1

        best = candidates[0] if len(candidates) == 1 else None
        results.append(
            {
                "person_index": idx,
                "person_name": full_name,
                "confidence": confidence,
                "auto_apply": auto_apply,
                "candidates": candidates,
                "reservation_id": best["reservation_id"] if best else None,
                "guest_id": best["guest_id"] if best else None,
                "guest_name": best["guest_name"] if best else "",
                "reservation_label": best["reservation_label"] if best else "",
            }
        )

    return results


def _reservation_label(reservation: Reservation) -> str:
    booker = (reservation.booker_name or "").strip()
    unit = ""
    try:
        ru = reservation.reservation_units.select_related("unit").first()
        if ru and ru.unit:
            unit = ru.unit.name or ru.unit.code or ""
    except Exception:
        pass
    parts = [f"#{reservation.pk}"]
    if booker:
        parts.append(booker)
    if unit:
        parts.append(unit)
    parts.append(reservation.check_in_date.isoformat())
    return " · ".join(parts)


def _confidence_for_candidates(candidates: list[dict], keys: set[str]) -> str:
    if not candidates:
        return "none"
    if len(candidates) == 1 and candidates[0].get("match_type") == "name":
        return "high"
    if len(candidates) == 1:
        return "medium"
    name_matches = [c for c in candidates if c.get("match_type") == "name"]
    if len(name_matches) == 1:
        return "high"
    return "low"


def normalize_mrz_lines(person: dict) -> str:
    lines = person.get("mrz_lines") or []
    if isinstance(lines, list):
        cleaned = [re.sub(r"\s+", "", str(line).upper()) for line in lines if str(line).strip()]
        return "\n".join(cleaned)
    return str(lines or "").strip()
