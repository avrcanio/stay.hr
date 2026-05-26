from __future__ import annotations

from typing import TypedDict


class UnitOccupancySpec(TypedDict):
    capacity_max_guests: int
    capacity_adults: int
    capacity_children: int
    capacity_infants: int


# Booking.com + Channex production (Luxury Room Uzorita B&B, May 2026).
UZORITA_UNIT_OCCUPANCY: dict[str, UnitOccupancySpec] = {
    "R1": {
        "capacity_max_guests": 2,
        "capacity_adults": 2,
        "capacity_children": 1,
        "capacity_infants": 1,
    },
    "R2": {
        "capacity_max_guests": 3,
        "capacity_adults": 2,
        "capacity_children": 2,
        "capacity_infants": 1,
    },
    "R3": {
        "capacity_max_guests": 4,
        "capacity_adults": 3,
        "capacity_children": 3,
        "capacity_infants": 3,
    },
    "R6": {
        "capacity_max_guests": 4,
        "capacity_adults": 3,
        "capacity_children": 3,
        "capacity_infants": 3,
    },
}

UZORITA_OCCUPANCY_SEED_UNIT_CODES: tuple[str, ...] = tuple(UZORITA_UNIT_OCCUPANCY.keys())
