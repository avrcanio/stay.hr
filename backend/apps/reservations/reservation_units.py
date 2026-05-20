from __future__ import annotations

from decimal import Decimal

from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.reservations.unit_mapping import resolve_unit
from apps.tenants.models import Tenant


def joined_room_names(
    reservation: Reservation,
    *,
    units: list[ReservationUnit] | None = None,
) -> str:
    unit_list = units if units is not None else list(reservation.units.order_by("sort_order", "id"))
    return ", ".join(u.room_name for u in unit_list if u.room_name)


def split_room_names(room_name: str) -> list[str]:
    if not room_name:
        return []
    return [part.strip() for part in room_name.split(",") if part.strip()]


def split_unit_amounts(total_amount: Decimal, unit_count: int) -> list[Decimal]:
    if unit_count <= 0:
        return []
    base = (total_amount / unit_count).quantize(Decimal("0.01"))
    amounts = [base] * unit_count
    remainder = total_amount - sum(amounts)
    if remainder:
        amounts[-1] = (amounts[-1] + remainder).quantize(Decimal("0.01"))
    return amounts


def apply_unit_amounts_from_total(
    *,
    reservation: Reservation,
    total_amount: Decimal | None,
    units: list[ReservationUnit] | None = None,
) -> None:
    unit_list = units if units is not None else list(reservation.units.order_by("sort_order", "id"))
    if not unit_list or total_amount is None:
        return
    for unit, amount in zip(unit_list, split_unit_amounts(total_amount, len(unit_list))):
        if unit.amount != amount:
            unit.amount = amount
            unit.save(update_fields=["amount", "updated_at"])


def sync_reservation_units(
    *,
    tenant: Tenant,
    property: Property,
    reservation: Reservation,
    room_name: str,
) -> list[ReservationUnit]:
    segments = split_room_names(room_name) or [room_name or "Unknown"]
    existing = {u.sort_order: u for u in reservation.units.all()}
    kept_ids: list[int] = []

    for idx, segment in enumerate(segments):
        display_name = segment.strip() or "Unknown"
        unit = resolve_unit(tenant=tenant, property=property, room_name=display_name)
        row = existing.get(idx)
        if row is None:
            row = ReservationUnit.objects.create(
                tenant=tenant,
                reservation=reservation,
                sort_order=idx,
                room_name=display_name,
                unit=unit,
            )
        else:
            changed_fields: list[str] = []
            if row.room_name != display_name:
                row.room_name = display_name
                changed_fields.append("room_name")
            if row.unit_id != (unit.id if unit else None):
                row.unit = unit
                changed_fields.append("unit")
            if changed_fields:
                changed_fields.append("updated_at")
                row.save(update_fields=changed_fields)
        kept_ids.append(row.id)

    reservation.units.exclude(id__in=kept_ids).delete()
    return list(reservation.units.order_by("sort_order", "id"))
