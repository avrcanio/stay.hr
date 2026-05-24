"""Shared availability rules for public booking and reception calendar."""

from __future__ import annotations

from datetime import date, timedelta

from apps.integrations.models import UnitAvailabilityBlock, UnitAvailabilityDay
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


def stay_nights(check_in: date, check_out: date) -> list[date]:
    """Hotel nights covered by [check_in, check_out)."""
    nights: list[date] = []
    current = check_in
    while current < check_out:
        nights.append(current)
        current += timedelta(days=1)
    return nights


def unit_has_closed_ari_nights(
    tenant: Tenant,
    unit_id: int,
    check_in: date,
    check_out: date,
) -> bool:
    nights = stay_nights(check_in, check_out)
    if not nights:
        return False
    return UnitAvailabilityDay.objects.filter(
        tenant=tenant,
        unit_id=unit_id,
        date__in=nights,
        availability__lte=0,
    ).exists()


def _closed_ari_blocks_range(
    tenant: Tenant,
    unit_id: int,
    check_in: date,
    check_out: date,
    *,
    exclude_reservation_id: int | None = None,
) -> bool:
    excluded_stay: tuple[date, date] | None = None
    if exclude_reservation_id is not None:
        excluded = (
            Reservation.objects.filter(pk=exclude_reservation_id, tenant=tenant)
            .values_list("check_in", "check_out")
            .first()
        )
        if excluded is not None:
            excluded_stay = excluded

    for night in stay_nights(check_in, check_out):
        if excluded_stay is not None:
            stay_in, stay_out = excluded_stay
            if stay_in <= night < stay_out:
                continue
        if unit_has_closed_ari_nights(tenant, unit_id, night, night + timedelta(days=1)):
            return True
    return False


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

    if exclude_reservation_id is not None:
        if _closed_ari_blocks_range(
            tenant,
            unit_id,
            check_in,
            check_out,
            exclude_reservation_id=exclude_reservation_id,
        ):
            return True
    elif unit_has_closed_ari_nights(tenant, unit_id, check_in, check_out):
        return True

    return False


def unit_blocked_nights(
    tenant: Tenant,
    unit_id: int,
    from_date: date,
    to_date: date,
    *,
    exclude_reservation_id: int | None = None,
) -> list[date]:
    """Return individual nights in [from_date, to_date) that block booking."""
    return [
        night
        for night in stay_nights(from_date, to_date)
        if unit_has_blocking_overlap(
            tenant,
            unit_id,
            night,
            night + timedelta(days=1),
            exclude_reservation_id=exclude_reservation_id,
        )
    ]


def validate_unit_available_for_booking(
    tenant: Tenant,
    unit: Unit,
    check_in: date,
    check_out: date,
    *,
    exclude_reservation_id: int | None = None,
) -> None:
    if unit_has_blocking_overlap(
        tenant,
        unit.id,
        check_in,
        check_out,
        exclude_reservation_id=exclude_reservation_id,
    ):
        raise ValueError("Unit is not available for the selected dates.")
