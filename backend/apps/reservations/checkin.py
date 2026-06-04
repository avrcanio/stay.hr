from __future__ import annotations

from datetime import date

from apps.core.timezone import property_local_now
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant


class CheckInBlockedError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _reservation_unit_ids(reservation: Reservation) -> list[int]:
    if hasattr(reservation, "_prefetched_objects_cache") and "units" in getattr(
        reservation, "_prefetched_objects_cache", {}
    ):
        links = reservation.units.all()
    else:
        links = ReservationUnit.objects.filter(reservation_id=reservation.pk)
    return [link.unit_id for link in links if link.unit_id is not None]


def unit_has_checked_in_guest(
    tenant: Tenant,
    unit_id: int,
    *,
    today: date,
    exclude_reservation_id: int | None = None,
) -> bool:
    qs = ReservationUnit.objects.filter(
        tenant=tenant,
        unit_id=unit_id,
        reservation__status=Reservation.Status.CHECKED_IN,
        reservation__check_out__gt=today,
    )
    if exclude_reservation_id is not None:
        qs = qs.exclude(reservation_id=exclude_reservation_id)
    return qs.exists()


def validate_reservation_check_in(reservation: Reservation, *, tenant: Tenant) -> None:
    today = property_local_now(reservation.property).date()
    if today != reservation.check_in:
        raise CheckInBlockedError(
            "wrong_date",
            "Check-in je moguć samo na dan dolaska.",
        )

    unit_ids = _reservation_unit_ids(reservation)
    if not unit_ids:
        raise CheckInBlockedError(
            "no_unit",
            "Rezervacija nema dodijeljenu sobu.",
        )

    for unit_id in unit_ids:
        if unit_has_checked_in_guest(
            tenant,
            unit_id,
            today=today,
            exclude_reservation_id=reservation.pk,
        ):
            raise CheckInBlockedError(
                "room_occupied",
                "Soba je zauzeta — drugi gost je već prijavljen.",
            )


def get_check_in_block_reason(
    reservation: Reservation,
    *,
    tenant: Tenant,
) -> CheckInBlockedError | None:
    try:
        validate_reservation_check_in(reservation, tenant=tenant)
    except CheckInBlockedError as exc:
        return exc
    return None
