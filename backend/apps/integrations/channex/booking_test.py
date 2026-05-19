"""
Booking.com test hotel (Channex certification) room definitions.

Hotel ID: 10745030 (Channex suggested test account, GBP)
Channel ID: 10c89e90-c552-4fe6-ab33-49ec1b7b2721
"""

from __future__ import annotations

from typing import TypedDict

from apps.integrations.channex.demo_property import CHANNEX_CERT_TENANT_SLUG

# Demo tenant channel → Test Property - Stay.hr (Booking.com test hotel 10745030)
CHANNEX_BOOKING_TEST_CHANNEL_ID = "8ee9c7aa-6433-4037-924b-4f95598782d5"
BOOKING_COM_TEST_HOTEL_ID = "10745030"

# Property slug on uzorita (legacy); certification uses channex-demo on tenant demo.
CHANNEX_BOOKING_TEST_PROPERTY_SLUG = "channex-bcom-test"


def certification_property_slug(tenant_slug: str | None = None) -> str:
    from apps.integrations.channex.demo_property import (
        CHANNEX_CERT_TENANT_SLUG,
        CHANNEX_DEMO_PROPERTY_SLUG,
    )

    slug = (tenant_slug or CHANNEX_CERT_TENANT_SLUG).strip()
    if slug == CHANNEX_CERT_TENANT_SLUG:
        return CHANNEX_DEMO_PROPERTY_SLUG
    return CHANNEX_BOOKING_TEST_PROPERTY_SLUG


def booking_test_room_types_config_payload(
    tenant_slug: str | None = None,
    property_slug: str | None = None,
) -> list[dict[str, str | int]]:
    """Booking.com test room types with unit_id for certification property."""
    from apps.properties.models import Property, Unit
    from apps.tenants.models import Tenant

    prop_slug = property_slug or certification_property_slug(tenant_slug)
    tenant = Tenant.objects.filter(slug=tenant_slug or CHANNEX_CERT_TENANT_SLUG).first()
    if tenant is None:
        return [
            {
                "unit_code": row["unit_code"],
                "channex_room_type_id": row["channex_room_type_id"],
                "channex_title": row["channex_title"],
            }
            for row in BOOKING_COM_TEST_ROOMS
        ]

    prop = Property.objects.filter(tenant=tenant, slug=prop_slug).first()
    payload: list[dict[str, str | int]] = []
    for spec in BOOKING_COM_TEST_ROOMS:
        item: dict[str, str | int] = {
            "unit_code": spec["unit_code"],
            "channex_room_type_id": spec["channex_room_type_id"],
            "channex_title": spec["channex_title"],
        }
        if prop is not None:
            unit = Unit.objects.filter(
                tenant=tenant, property=prop, code=spec["unit_code"]
            ).first()
            if unit is not None:
                item["unit_id"] = unit.id
        payload.append(item)
    return payload


class BookingTestRatePlanSpec(TypedDict):
    code: str
    title: str
    channex_rate_plan_id: str
    default_gbp: str
    booking_rate_id: str


class BookingTestRoomSpec(TypedDict):
    unit_code: str
    name: str
    booking_room_id: str
    booking_title: str
    capacity_adults: int
    capacity_children: int
    channex_room_type_id: str
    channex_title: str
    rate_plans: list[BookingTestRatePlanSpec]


BOOKING_COM_TEST_ROOMS: tuple[BookingTestRoomSpec, ...] = (
    {
        "unit_code": "BCOM-HOLIDAY",
        "name": "Holiday Home (Booking test)",
        "booking_room_id": "1074503007",
        "booking_title": "Holiday Home",
        "capacity_adults": 11,
        "capacity_children": 0,
        "channex_room_type_id": "430b1381-dace-44d6-8d5d-a0a1025819fc",
        "channex_title": "Holiday Home",
        "rate_plans": [
            {
                "code": "standard",
                "title": "Standard rate",
                "channex_rate_plan_id": "81061916-cc0a-4b78-850e-2d6d4be7c551",
                "default_gbp": "165.00",
                "booking_rate_id": "39950621",
            },
            {
                "code": "non_refundable",
                "title": "non-refundable rate",
                "channex_rate_plan_id": "69f4bf3b-e23a-409e-be16-50a0f2b17605",
                "default_gbp": "135.00",
                "booking_rate_id": "39950622",
            },
        ],
    },
    {
        "unit_code": "BCOM-STUDIO",
        "name": "Studio (Booking test)",
        "booking_room_id": "1074503008",
        "booking_title": "Studio",
        "capacity_adults": 2,
        "capacity_children": 0,
        "channex_room_type_id": "18c437d7-13e3-4dbc-9565-48fad4832bf5",
        "channex_title": "Studio",
        "rate_plans": [
            {
                "code": "standard",
                "title": "Standard rate",
                "channex_rate_plan_id": "aa73125c-b9b6-48a7-862f-da68c6e77999",
                "default_gbp": "95.00",
                "booking_rate_id": "39950621",
            },
            {
                "code": "non_refundable",
                "title": "non-refundable rate",
                "channex_rate_plan_id": "6734ae1e-70bb-4217-b668-2aa8720bca13",
                "default_gbp": "79.00",
                "booking_rate_id": "39950622",
            },
        ],
    },
)
