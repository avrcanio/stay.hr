from __future__ import annotations

from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant

PLACEHOLDER_FIRST = "Novi"
PLACEHOLDER_LAST = "gost"
PLACEHOLDER_NAME = "Novi gost"


def target_adult_guest_count(*, adults_count: int | None, existing_count: int) -> int:
    """Minimum guest records that should exist for adult slots."""
    base = adults_count if adults_count and adults_count > 0 else existing_count
    return max(base, existing_count, 1)


def ensure_adult_guest_slots(
    *,
    tenant: Tenant,
    reservation: Reservation,
    adults_count: int | None,
) -> int:
    """Add placeholder guests until count matches adults_count. Returns number created."""
    if reservation.status == Reservation.Status.CANCELED:
        return 0

    existing_count = reservation.guests.count()
    target = target_adult_guest_count(
        adults_count=adults_count,
        existing_count=existing_count,
    )
    created = 0
    for _ in range(target - existing_count):
        Guest.objects.create(
            tenant=tenant,
            reservation=reservation,
            first_name=PLACEHOLDER_FIRST,
            last_name=PLACEHOLDER_LAST,
            name=PLACEHOLDER_NAME,
            is_primary=False,
        )
        created += 1
    return created
