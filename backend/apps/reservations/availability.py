"""Shared availability rules for public booking and reception calendar."""

from __future__ import annotations

from datetime import date

from apps.integrations.models import UnitAvailabilityBlock
from apps.properties.models import Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant

# Statuses that block public booking search / create validation.
BLOCKING_RESERVATION_STATUSES = frozenset(
    {
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
    }
)

# Statuses shown on reception room calendar (excludes pending/refused/canceled).
CALENDAR_RESERVATION_STATUSES = frozenset(
    {
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CHECKED_OUT,
    }
)


def unit_has_blocking_overlap(
    tenant: Tenant,
    unit_id: int,
    check_in: date,
    check_out: date,
    *,
    exclude_reservation_id: int | None = None,
) -> bool:
    """Return True if the unit is unavailable for [check_in, check_out)."""
    reservation_qs = ReservationUnit.objects.filter(
        tenant=tenant,
        unit_id=unit_id,
        reservation__status__in=BLOCKING_RESERVATION_STATUSES,
        reservation__check_in__lt=check_out,
        reservation__check_out__gt=check_in,
    )
    if exclude_reservation_id is not None:
        reservation_qs = reservation_qs.exclude(reservation_id=exclude_reservation_id)
    if reservation_qs.exists():
        return True

    block_qs = UnitAvailabilityBlock.objects.filter(
        tenant=tenant,
        unit_id=unit_id,
        check_in__lt=check_out,
        check_out__gt=check_in,
    )
    if block_qs.exists():
        return True

    return False


def validate_unit_available_for_booking(
    tenant: Tenant,
    unit: Unit,
    check_in: date,
    check_out: date,
) -> None:
    if unit_has_blocking_overlap(tenant, unit.id, check_in, check_out):
        raise ValueError("Unit is not available for the selected dates.")
