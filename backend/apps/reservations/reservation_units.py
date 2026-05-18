from __future__ import annotations

from apps.reservations.models import Reservation, ReservationUnit


def joined_room_names(
    reservation: Reservation,
    *,
    units: list[ReservationUnit] | None = None,
) -> str:
    unit_list = units if units is not None else list(reservation.units.order_by("sort_order", "id"))
    return ", ".join(u.room_name for u in unit_list if u.room_name)
