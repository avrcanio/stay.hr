"""Operator WhatsApp: pick reservation when document match is ambiguous."""

from __future__ import annotations

from apps.reservations.document_intake_match import (
    active_reservations_for_intake,
    _person_full_name,
)
from apps.reservations.guest_slots import is_unfilled_guest
from apps.reservations.models import DocumentIntakeJob, Reservation

_MAX_PICK_LINES = 8


def _reservation_unit_label(reservation: Reservation) -> str:
    try:
        ru = reservation.units.select_related("unit").first()
        if ru and ru.unit:
            return (ru.unit.name or ru.unit.code or "").strip()
    except Exception:
        pass
    return ""


def _reservation_nights(reservation: Reservation) -> int:
    if reservation.nights_count:
        return int(reservation.nights_count)
    return max((reservation.check_out - reservation.check_in).days, 1)


def _unfilled_guest_count(reservation: Reservation) -> int:
    return sum(1 for guest in reservation.guests.all() if is_unfilled_guest(guest))


def format_reservation_pick_line(reservation: Reservation) -> str:
    booking = (reservation.booking_code or reservation.external_id or "").strip()
    unit = _reservation_unit_label(reservation)
    nights = _reservation_nights(reservation)
    night_label = "1 noć" if nights == 1 else f"{nights} noći"
    dates = (
        f"{reservation.check_in:%d.%m}–{reservation.check_out:%d.%m}"
    )
    booker = (reservation.booker_name or "").strip()
    unfilled = _unfilled_guest_count(reservation)
    slot_label = (
        "1 prazan slot"
        if unfilled == 1
        else f"{unfilled} prazni slotovi"
        if unfilled > 1
        else "bez praznih slotova"
    )

    parts = [f"#{reservation.pk}"]
    if booking:
        parts.append(f"BK {booking}")
    if unit:
        parts.append(f"soba {unit}")
    parts.append(f"{night_label} ({dates})")
    if booker:
        parts.append(booker)
    parts.append(slot_label)
    return " · ".join(parts)


def collect_pick_candidate_reservation_ids(
    matches: list[dict],
    *,
    tenant_id: int,
) -> list[int]:
    ids: set[int] = set()
    for match in matches:
        if not isinstance(match, dict):
            continue
        if match.get("auto_apply") and match.get("reservation_id") is not None:
            ids.add(int(match["reservation_id"]))
        if match.get("reservation_id") is not None and not match.get("auto_apply"):
            ids.add(int(match["reservation_id"]))
        for candidate in match.get("candidates") or []:
            if isinstance(candidate, dict) and candidate.get("reservation_id") is not None:
                ids.add(int(candidate["reservation_id"]))

    if not ids:
        for reservation in active_reservations_for_intake(tenant_id):
            ids.add(reservation.pk)

    reservations = list(
        Reservation.objects.filter(pk__in=ids).prefetch_related("guests").order_by(
            "check_in", "id"
        )
    )
    return [r.pk for r in reservations[:_MAX_PICK_LINES]]


def build_operator_reservation_pick_message(job: DocumentIntakeJob) -> str:
    persons = (job.ocr_result or {}).get("persons") or []
    person_lines = [
        f"• {_person_full_name(person)}"
        for person in persons
        if isinstance(person, dict) and _person_full_name(person)
    ]
    reservation_ids = collect_pick_candidate_reservation_ids(
        job.matches or [],
        tenant_id=job.tenant_id,
    )
    reservations = list(
        Reservation.objects.filter(pk__in=reservation_ids)
        .prefetch_related("guests", "units__unit")
        .order_by("check_in", "id")
    )

    lines = [
        "Imena s dokumenta ne poklapaju jednoznačno s rezervacijom.",
    ]
    if person_lines:
        lines.append("")
        lines.extend(person_lines)
    lines.append("")
    lines.append("Pošaljite #rezervacije ili Booking broj.")
    if reservations:
        lines.append("")
        for index, reservation in enumerate(reservations, start=1):
            lines.append(f"{index}) {format_reservation_pick_line(reservation)}")

    body = "\n".join(lines)
    return body[:1024]
