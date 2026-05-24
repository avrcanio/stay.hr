from __future__ import annotations

from django.utils import timezone

from apps.integrations.whatsapp.phone import phones_match
from apps.reservations.models import Guest, Reservation


ACTIVE_STATUSES = frozenset(
    {
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
    }
)


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
