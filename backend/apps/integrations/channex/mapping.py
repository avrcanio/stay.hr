"""
Channex staging room type UUIDs for Uzorita (4 physical units).

Created on Channex staging property "Uzorita" — one room type per physical unit (count=1).
"""

from __future__ import annotations

from typing import TypedDict


class ChannexRoomTypeMapping(TypedDict):
    unit_code: str
    channex_room_type_id: str
    channex_title: str


UZORITA_STAGING_ROOM_TYPES: tuple[ChannexRoomTypeMapping, ...] = (
    {
        "unit_code": "R1",
        "channex_room_type_id": "e8fc8060-3df5-4e49-bee9-32903786b4ee",
        "channex_title": "Deluxe King 1",
    },
    {
        "unit_code": "R2",
        "channex_room_type_id": "0d852a5e-41d5-4801-9bf1-679deabcfbec",
        "channex_title": "Luxury Room Uzorita - R2",
    },
    {
        "unit_code": "D1",
        "channex_room_type_id": "ecc2d4ab-7894-4fc9-8e20-c08d2317e4be",
        "channex_title": "Deluxe Double",
    },
    {
        "unit_code": "R3",
        "channex_room_type_id": "6058e4da-0ed4-48a1-a877-fec38685589a",
        "channex_title": "Luxury Room Uzorita - R3",
    },
)


def room_types_config_payload() -> list[dict[str, str | int]]:
    """Build config.room_types list with stay Unit.id when units exist."""
    from django.db.models import Count

    from apps.properties.models import Unit
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(slug="uzorita").first()
    if tenant is None:
        return [{**row} for row in UZORITA_STAGING_ROOM_TYPES]

    units_by_code: dict[str, Unit] = {}
    for unit in (
        Unit.objects.filter(tenant=tenant, is_active=True)
        .annotate(reservation_links=Count("reservation_units"))
        .order_by("code", "-reservation_links", "-id")
    ):
        units_by_code.setdefault(unit.code, unit)

    payload: list[dict[str, str | int]] = []
    for row in UZORITA_STAGING_ROOM_TYPES:
        item: dict[str, str | int] = dict(row)
        unit = units_by_code.get(row["unit_code"])
        if unit is not None:
            item["unit_id"] = unit.id
        payload.append(item)
    return payload
