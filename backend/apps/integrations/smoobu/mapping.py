"""
Smoobu apartment IDs for Uzorita (Advanced → API Keys → Accommodations).

Live Booking.com listings for R1–R6 are managed in Smoobu, not Channex.
"""

from __future__ import annotations

from typing import TypedDict


class SmoobuApartmentMapping(TypedDict):
    unit_code: str
    smoobu_apartment_id: int


UZORITA_SMOOBU_APARTMENTS: tuple[SmoobuApartmentMapping, ...] = (
    {"unit_code": "R1", "smoobu_apartment_id": 3327457},
    {"unit_code": "R2", "smoobu_apartment_id": 3327482},
    {"unit_code": "R3", "smoobu_apartment_id": 3327487},
    {"unit_code": "R6", "smoobu_apartment_id": 3328822},
)

SMOOBU_API_BASE = "https://login.smoobu.com"
UZORITA_SETTINGS_CHANNEL_ID = 6538582


def apartments_config_payload() -> list[dict[str, str | int]]:
    """Build config.apartments with stay Unit.id when units exist."""
    from django.db.models import Count

    from apps.properties.models import Unit
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(slug="uzorita").first()
    if tenant is None:
        return [{**row} for row in UZORITA_SMOOBU_APARTMENTS]

    units_by_code: dict[str, Unit] = {}
    for unit in (
        Unit.objects.filter(tenant=tenant, is_active=True)
        .annotate(reservation_links=Count("reservation_units"))
        .order_by("code", "-reservation_links", "-id")
    ):
        units_by_code.setdefault(unit.code, unit)

    payload: list[dict[str, str | int]] = []
    for row in UZORITA_SMOOBU_APARTMENTS:
        item: dict[str, str | int] = dict(row)
        unit = units_by_code.get(row["unit_code"])
        if unit is not None:
            item["unit_id"] = unit.id
        payload.append(item)
    return payload
