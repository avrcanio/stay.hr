"""Kalendar agregacija soba-noći (kapacitet / rezervirano / realizirano) po mjesecu."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from apps.properties.models import Unit
from apps.reservations.availability import stay_nights
from apps.reservations.models import Reservation, ReservationUnit

_REALIZED_STATUSES = frozenset(
    {
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CHECKED_OUT,
    }
)
_RESERVED_STATUSES = frozenset(
    {
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CHECKED_OUT,
    }
)


def _empty_occupancy_bucket() -> dict:
    return {
        "capacity_room_nights": 0,
        "occupied_room_nights": 0,
        "reserved_room_nights": 0,
    }


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    days = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = start + timedelta(days=days)
    return start, end


def _nights_in_month(check_in: date, check_out: date, year: int, month: int) -> int:
    month_start, month_end = _month_bounds(year, month)
    if check_out <= month_start or check_in >= month_end:
        return 0
    clip_start = max(check_in, month_start)
    clip_end = min(check_out, month_end)
    if clip_end <= clip_start:
        return 0
    return len(stay_nights(clip_start, clip_end))


def _pct_str(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0"
    pct = (Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(
        Decimal("0.1")
    )
    return format(pct, "f")


def _active_unit_count(tenant) -> int:
    return Unit.objects.for_tenant(tenant).filter(is_active=True).count()


def _capacity_for_month(active_units: int, year: int, month: int) -> int:
    if active_units <= 0:
        return 0
    return active_units * calendar.monthrange(year, month)[1]


def aggregate_monthly_occupancy(tenant, year: int) -> dict:
    """
    Return occupancy buckets keyed by month for current and comparison year.

    Structure:
        {
            "active_units": int,
            "months": {
                month: {
                    "current": {...},
                    "previous": {...},
                }
            },
        }
    """
    comparison_year = year - 1
    active_units = _active_unit_count(tenant)

    buckets: dict[int, dict[str, dict]] = {
        month: {
            "current": _empty_occupancy_bucket(),
            "previous": _empty_occupancy_bucket(),
        }
        for month in range(1, 13)
    }

    for month in range(1, 13):
        for slot_key, slot_year in (("current", year), ("previous", comparison_year)):
            cap = _capacity_for_month(active_units, slot_year, month)
            buckets[month][slot_key]["capacity_room_nights"] = cap

    range_start = date(comparison_year, 1, 1)
    range_end = date(year, 12, 31)

    reservation_rows = (
        Reservation.objects.for_tenant(tenant)
        .filter(
            status__in=_RESERVED_STATUSES,
            check_in__lte=range_end,
            check_out__gt=range_start,
        )
        .prefetch_related("units")
        .only("check_in", "check_out", "status", "units_count")
    )

    for reservation in reservation_rows.iterator():
        check_in = reservation.check_in
        check_out = reservation.check_out
        if check_in is None or check_out is None:
            continue

        unit_rows = list(reservation.units.all())
        if unit_rows:
            unit_multiplier = len(unit_rows)
        else:
            unit_multiplier = max(int(reservation.units_count or 0), 1)

        is_realized = reservation.status in _REALIZED_STATUSES
        is_reserved = reservation.status in _RESERVED_STATUSES

        for slot_year, slot_key in ((year, "current"), (comparison_year, "previous")):
            for month in range(1, 13):
                nights = _nights_in_month(check_in, check_out, slot_year, month)
                if nights <= 0:
                    continue
                room_nights = nights * unit_multiplier
                slot = buckets[month][slot_key]
                if is_reserved:
                    slot["reserved_room_nights"] += room_nights
                if is_realized:
                    slot["occupied_room_nights"] += room_nights

    return {
        "active_units": active_units,
        "months": buckets,
    }


def occupancy_payload_for_month(bucket: dict) -> dict:
    capacity = bucket["capacity_room_nights"]
    occupied = bucket["occupied_room_nights"]
    reserved = bucket["reserved_room_nights"]
    return {
        "capacity_room_nights": capacity,
        "occupied_room_nights": occupied,
        "reserved_room_nights": reserved,
        "occupancy_realized_pct": _pct_str(occupied, capacity),
        "occupancy_reserved_pct": _pct_str(reserved, capacity),
    }
