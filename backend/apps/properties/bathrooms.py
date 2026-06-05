from __future__ import annotations

from typing import TypedDict


class UnitBathroomSpec(TypedDict):
    is_private: bool
    is_inside_room: bool
    sort_order: int


UZORITA_STANDARD_BATHROOM: UnitBathroomSpec = {
    "is_private": True,
    "is_inside_room": True,
    "sort_order": 0,
}

UZORITA_BATHROOM_SEED_UNIT_CODES: tuple[str, ...] = ("R1", "R2", "R3", "R4", "R6")
