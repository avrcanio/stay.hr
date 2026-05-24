from datetime import date
from decimal import Decimal

from apps.tourist_tax.models import (
    TouristTaxAccommodationCategory,
    TouristTaxAgeBracket,
    TouristTaxOrdinance,
    TouristTaxRate,
    TouristTaxSeason,
    TouristTaxZone,
)

CATEGORIES = [
    {"code": "room", "name": "Sobe"},
    {"code": "apartment", "name": "Apartmani"},
    {"code": "hotel", "name": "Hoteli"},
]

SEASONS = [
    {
        "code": "main",
        "kind": TouristTaxSeason.Kind.MAIN,
        "start_month": 4,
        "start_day": 1,
        "end_month": 9,
        "end_day": 30,
    },
    {
        "code": "off",
        "kind": TouristTaxSeason.Kind.OFF,
        "start_month": 10,
        "start_day": 1,
        "end_month": 3,
        "end_day": 31,
    },
]

AGE_BRACKETS = [
    {
        "code": "child",
        "min_age": 0,
        "max_age": 11,
        "multiplier": Decimal("0.00"),
        "sort_order": 0,
    },
    {
        "code": "youth",
        "min_age": 12,
        "max_age": 17,
        "multiplier": Decimal("0.50"),
        "sort_order": 1,
    },
    {
        "code": "adult",
        "min_age": 18,
        "max_age": None,
        "multiplier": Decimal("1.00"),
        "sort_order": 2,
    },
]


def seed_ordinance(
    *,
    code: str,
    name: str,
    issuer: str,
    valid_from: date,
    zones: list[dict],
    stdout=None,
) -> tuple[TouristTaxOrdinance, int]:
    """Seed one ordinance with zones, seasons, categories, age brackets and rates."""
    write = stdout.write if stdout else print

    ordinance, created = TouristTaxOrdinance.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "issuer": issuer,
            "valid_from": valid_from,
            "valid_to": None,
            "currency": "EUR",
            "is_active": True,
        },
    )
    action = "Created" if created else "Updated"
    write(f"{action} ordinance: {ordinance.code}")

    categories: dict[str, TouristTaxAccommodationCategory] = {}
    for item in CATEGORIES:
        category, _ = TouristTaxAccommodationCategory.objects.update_or_create(
            code=item["code"],
            defaults={"name": item["name"]},
        )
        categories[item["code"]] = category

    seasons: dict[str, TouristTaxSeason] = {}
    for item in SEASONS:
        season, _ = TouristTaxSeason.objects.update_or_create(
            ordinance=ordinance,
            code=item["code"],
            defaults={
                "kind": item["kind"],
                "start_month": item["start_month"],
                "start_day": item["start_day"],
                "end_month": item["end_month"],
                "end_day": item["end_day"],
            },
        )
        seasons[item["code"]] = season

    for item in AGE_BRACKETS:
        TouristTaxAgeBracket.objects.update_or_create(
            ordinance=ordinance,
            code=item["code"],
            defaults={
                "min_age": item["min_age"],
                "max_age": item["max_age"],
                "multiplier": item["multiplier"],
                "sort_order": item["sort_order"],
            },
        )

    rate_count = 0
    for zone_data in zones:
        zone, _ = TouristTaxZone.objects.update_or_create(
            ordinance=ordinance,
            code=zone_data["code"],
            defaults={
                "name": zone_data["name"],
                "kind": zone_data["kind"],
                "settlements": zone_data["settlements"],
            },
        )
        for season_code, amount in zone_data["rates"].items():
            for category in categories.values():
                TouristTaxRate.objects.update_or_create(
                    zone=zone,
                    season=seasons[season_code],
                    category=category,
                    defaults={"amount": amount},
                )
                rate_count += 1
        write(
            f"Zone {zone.code}: main={zone_data['rates']['main']} €, "
            f"off={zone_data['rates']['off']} €"
        )

    return ordinance, rate_count
