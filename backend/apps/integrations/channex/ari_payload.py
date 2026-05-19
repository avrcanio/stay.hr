from __future__ import annotations

from decimal import Decimal
from typing import Any


def rate_to_channex_value(rate: Decimal) -> str:
    return format(rate.quantize(Decimal("0.01")), "f")


def build_availability_value(
    *,
    property_id: str,
    room_type_id: str,
    availability: int,
    day: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "property_id": property_id,
        "room_type_id": room_type_id,
        "availability": max(0, int(availability)),
    }
    if day:
        row["date"] = day
    else:
        row["date_from"] = date_from
        row["date_to"] = date_to
    return row


def build_restriction_value(
    *,
    property_id: str,
    rate_plan_id: str,
    day: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    rate: Decimal | None = None,
    min_stay_arrival: int | None = None,
    min_stay_through: int | None = None,
    min_stay: int | None = None,
    max_stay: int | None = None,
    stop_sell: bool | None = None,
    closed_to_arrival: bool | None = None,
    closed_to_departure: bool | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "property_id": property_id,
        "rate_plan_id": rate_plan_id,
    }
    if day:
        row["date"] = day
    else:
        row["date_from"] = date_from
        row["date_to"] = date_to
    if rate is not None:
        row["rate"] = rate_to_channex_value(rate)
    if min_stay_arrival is not None:
        row["min_stay_arrival"] = int(min_stay_arrival)
    if min_stay_through is not None:
        row["min_stay_through"] = int(min_stay_through)
    if min_stay is not None:
        row["min_stay"] = int(min_stay)
    if max_stay is not None:
        row["max_stay"] = int(max_stay)
    if stop_sell is not None:
        row["stop_sell"] = bool(stop_sell)
    if closed_to_arrival is not None:
        row["closed_to_arrival"] = bool(closed_to_arrival)
    if closed_to_departure is not None:
        row["closed_to_departure"] = bool(closed_to_departure)
    return row
