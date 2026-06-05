"""Match OCR persons to active reservations and guest slots."""

from __future__ import annotations

import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.reservations.booking_xls_import import (
    _guest_display_name,
    _normalize_guest_name_key,
)
from apps.reservations.guest_slots import PLACEHOLDER_NAME, is_unfilled_guest
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
            check_in__lte=window_end,
            check_out__gte=window_start,
        )
        .prefetch_related("guests")
        .order_by("check_in", "id")
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


def _fuzzy_guest_match(
    reservation: Reservation,
    keys: set[str],
    *,
    exclude: set[int] | None = None,
) -> Guest | None:
    blocked = exclude or set()
    for guest in reservation.guests.all():
        if guest.pk in blocked:
            continue
        if _guest_name_matches(guest, keys):
            return guest
    return None


def _is_placeholder_guest(guest: Guest) -> bool:
    name = (guest.name or "").strip()
    if name == PLACEHOLDER_NAME:
        return True
    first = (guest.first_name or "").strip()
    last = (guest.last_name or "").strip()
    return first == "Novi" and last == "gost"


def _find_unfilled_slot(
    reservation: Reservation,
    *,
    exclude: set[int] | None = None,
) -> Guest | None:
    """Prefer secondary placeholders over primary booker slots still missing ID data."""
    blocked = exclude or set()
    unfilled: list[Guest] = []
    for guest in reservation.guests.all():
        if guest.pk in blocked:
            continue
        if is_unfilled_guest(guest):
            unfilled.append(guest)

    if not unfilled:
        return None

    for guest in unfilled:
        if not guest.is_primary and _is_placeholder_guest(guest):
            return guest

    for guest in unfilled:
        if not guest.is_primary:
            return guest

    return unfilled[0]


def _reservations_with_name_matches(results: list[dict]) -> set[int]:
    ids: set[int] = set()
    for result in results:
        for candidate in result.get("candidates") or []:
            if candidate.get("match_type") == "name":
                ids.add(int(candidate["reservation_id"]))
    return ids


def _apply_batch_reservation_heuristic(
    results: list[dict],
    *,
    reservations_by_id: dict[int, Reservation] | None = None,
) -> None:
    """When one reservation has a name match, auto-apply companions on the same reservation."""
    name_reservations = _reservations_with_name_matches(results)
    if len(name_reservations) != 1:
        return

    target_reservation_id = next(iter(name_reservations))
    reservation = None
    if reservations_by_id:
        reservation = reservations_by_id.get(target_reservation_id)
    if reservation is None:
        reservation = Reservation.objects.prefetch_related("guests").filter(pk=target_reservation_id).first()
    if reservation is None:
        return

    assigned_guest_ids = {
        int(result["guest_id"])
        for result in results
        if result.get("auto_apply") and result.get("guest_id")
    }

    for result in results:
        if result.get("auto_apply"):
            continue

        reservation_candidates = [
            candidate
            for candidate in result.get("candidates") or []
            if int(candidate["reservation_id"]) == target_reservation_id
            and int(candidate["guest_id"]) not in assigned_guest_ids
        ]
        guest = None
        if len(reservation_candidates) == 1:
            guest_id = int(reservation_candidates[0]["guest_id"])
            guest = next((g for g in reservation.guests.all() if g.pk == guest_id), None)
        if guest is None:
            guest = _find_unfilled_slot(reservation, exclude=assigned_guest_ids)
        if guest is None:
            continue

        result["auto_apply"] = True
        result["reservation_id"] = target_reservation_id
        result["guest_id"] = guest.pk
        result["guest_name"] = _guest_display_name(guest)
        result["reservation_label"] = _reservation_label(reservation)
        assigned_guest_ids.add(guest.pk)


def match_persons_to_guests(
    *,
    tenant_id: int,
    persons: list[dict],
) -> list[dict]:
    """Return match suggestions per person index."""
    reservations = active_reservations_for_intake(tenant_id)
    results: list[dict] = []
    assigned_guest_ids: set[int] = set()

    for idx, person in enumerate(persons):
        keys = _person_name_keys(person)
        full_name = _person_full_name(person)
        candidates: list[dict] = []

        for reservation in reservations:
            guest = None
            match_type = ""
            if keys:
                guest = _fuzzy_guest_match(reservation, keys, exclude=assigned_guest_ids)
                if guest:
                    match_type = "name"
            if guest is None:
                guest = _find_unfilled_slot(reservation, exclude=assigned_guest_ids)
                if guest:
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
                    "check_in_date": reservation.check_in.isoformat(),
                }
            )

        name_matches = [c for c in candidates if c.get("match_type") == "name"]
        if name_matches:
            # Jedinstveni name match — ne miješaj s praznim slotovima drugih rezervacija.
            candidates = name_matches

        confidence = _confidence_for_candidates(candidates, keys)
        if len(name_matches) == 1:
            best = name_matches[0]
            auto_apply = True
        elif len(candidates) == 1:
            best = candidates[0]
            auto_apply = True
        else:
            best = None
            auto_apply = False

        if best and auto_apply:
            assigned_guest_ids.add(int(best["guest_id"]))

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

    _apply_batch_reservation_heuristic(results)
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
    parts.append(reservation.check_in.isoformat())
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
