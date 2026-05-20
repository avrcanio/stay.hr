from __future__ import annotations

from typing import TypedDict


class UnitBedSpec(TypedDict):
    bed_type: str
    count: int
    sort_order: int


UZORITA_STANDARD_BEDS: tuple[UnitBedSpec, ...] = (
    {"bed_type": "queen", "count": 1, "sort_order": 0},
    {"bed_type": "sofa", "count": 1, "sort_order": 1},
)

UZORITA_BED_SEED_UNIT_CODES: tuple[str, ...] = ("R1", "R2", "R3", "R6")
