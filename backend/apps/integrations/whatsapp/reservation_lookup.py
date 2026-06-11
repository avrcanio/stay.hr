from __future__ import annotations

import re

from django.utils import timezone

from apps.integrations.whatsapp.phone import phones_match
from apps.reservations.models import Guest, Reservation

ACTIVE_STATUSES = frozenset(
    {
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
    }
)

_BOOKING_CODE_PREFIX_RE = re.compile(
    r"^(?:booking|buchung|reserva|réservation|reservation|kod|code|rezervacija)\s*[:#]?\s*",
    re.IGNORECASE,
)


def extract_booking_code_from_text(text: str) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    cleaned = _BOOKING_CODE_PREFIX_RE.sub("", raw).strip()
    if not cleaned:
        return None
    if re.fullmatch(r"[A-Za-z0-9\-]{4,64}", cleaned) and not cleaned.isdigit():
        return cleaned
    digits_only = re.sub(r"\D", "", cleaned)
    if len(digits_only) >= 6 and len(digits_only) <= 12:
        return digits_only
    if cleaned.isdigit() and 1 <= len(cleaned) <= 8:
        return cleaned
    return None


def find_reservation_by_booking_code(*, tenant_id: int, code: str) -> Reservation | None:
    code = (code or "").strip()
    if not code:
        return None

    if code.isdigit() and len(code) <= 8:
        pk_match = (
            Reservation.objects.filter(
                tenant_id=tenant_id,
                pk=int(code),
                status__in=ACTIVE_STATUSES,
            )
            .select_related("property", "tenant")
            .first()
        )
        if pk_match is not None:
            return pk_match

    qs = Reservation.objects.filter(
        tenant_id=tenant_id,
        status__in=ACTIVE_STATUSES,
        booking_code__iexact=code,
    ).select_related("property", "tenant")
    if not qs.exists():
        qs = Reservation.objects.filter(
            tenant_id=tenant_id,
            status__in=ACTIVE_STATUSES,
            external_id__iexact=code,
        ).select_related("property", "tenant")
    candidates = list(qs)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    today = timezone.localdate()
    return min(candidates, key=lambda row: abs((row.check_in - today).days))


def find_reservation_for_wa_id(*, tenant_id: int, wa_id: str) -> Reservation | None:
    wa_id = (wa_id or "").strip()
    if not wa_id:
        return None

    candidates: list[Reservation] = []
    seen_ids: set[int] = set()

    booker_qs = (
        Reservation.objects.filter(
            tenant_id=tenant_id,
            status__in=ACTIVE_STATUSES,
        )
        .exclude(booker_phone="")
        .select_related("property", "tenant")
    )
    for reservation in booker_qs:
        if phones_match(reservation.booker_phone, wa_id):
            if reservation.pk not in seen_ids:
                candidates.append(reservation)
                seen_ids.add(reservation.pk)

    guest_qs = (
        Guest.objects.filter(
            tenant_id=tenant_id,
            reservation__status__in=ACTIVE_STATUSES,
        )
        .exclude(phone="")
        .select_related("reservation", "reservation__property", "reservation__tenant")
    )
    for guest in guest_qs:
        reservation = guest.reservation
        if phones_match(guest.phone, wa_id) and reservation.pk not in seen_ids:
            candidates.append(reservation)
            seen_ids.add(reservation.pk)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    today = timezone.localdate()
    return min(candidates, key=lambda row: abs((row.check_in - today).days))
