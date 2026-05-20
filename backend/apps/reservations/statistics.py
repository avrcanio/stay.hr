"""Mjesečne agregacije prihoda, provizije i noći za recepcijsku statistiku."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.properties.models import Property
from apps.reservations.models import MonthlyStatisticsOverride, Reservation

DEFAULT_CURRENCY = "EUR"


def _property_label(tenant) -> str:
    properties = Property.objects.for_tenant(tenant).order_by("name")
    primary = properties.filter(slug=tenant.slug).first() or properties.first()
    if primary is not None:
        return primary.name
    return tenant.name


def _statistics_queryset(tenant, year: int):
    comparison_year = year - 1
    return (
        Reservation.objects.for_tenant(tenant)
        .filter(
            status__in=[
                Reservation.Status.CHECKED_IN,
                Reservation.Status.CHECKED_OUT,
            ],
            check_in__gte=date(comparison_year, 1, 1),
            check_in__lte=date(year, 12, 31),
        )
        .only(
            "check_in",
            "check_out",
            "amount",
            "commission_amount",
            "nights_count",
            "currency",
        )
    )


def _effective_nights(reservation: Reservation) -> int:
    if reservation.nights_count is not None:
        return int(reservation.nights_count)
    if reservation.check_in and reservation.check_out:
        return (reservation.check_out - reservation.check_in).days
    return 0


def _decimal_str(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def aggregate_monthly_statistics(tenant, year: int) -> dict:
    comparison_year = year - 1
    buckets: dict[int, dict[str, dict]] = {
        month: {
            "current": {
                "revenue": Decimal("0"),
                "commission": Decimal("0"),
                "nights": 0,
            },
            "previous": {
                "revenue": Decimal("0"),
                "commission": Decimal("0"),
                "nights": 0,
            },
        }
        for month in range(1, 13)
    }

    currency = DEFAULT_CURRENCY
    for reservation in _statistics_queryset(tenant, year).iterator():
        check_in = reservation.check_in
        if check_in is None:
            continue
        y = check_in.year
        if y == year:
            key = "current"
        elif y == comparison_year:
            key = "previous"
        else:
            continue

        month = check_in.month
        slot = buckets[month][key]
        slot["revenue"] += reservation.amount or Decimal("0")
        slot["commission"] += reservation.commission_amount or Decimal("0")
        slot["nights"] += _effective_nights(reservation)
        if reservation.currency:
            currency = reservation.currency

    overrides = {
        (row.year, row.month): row
        for row in MonthlyStatisticsOverride.objects.for_tenant(tenant).filter(
            year__in=[year, comparison_year],
        )
    }
    for month in range(1, 13):
        for key, target_year in (("current", year), ("previous", comparison_year)):
            override = overrides.get((target_year, month))
            if override is None:
                continue
            slot = buckets[month][key]
            slot["revenue"] = override.revenue
            slot["commission"] = override.commission or Decimal("0")
            slot["nights"] = override.nights
            if override.currency:
                currency = override.currency

    months_payload = []
    for month in range(1, 13):
        current = buckets[month]["current"]
        previous = buckets[month]["previous"]
        months_payload.append(
            {
                "month": month,
                "current": {
                    "revenue": _decimal_str(current["revenue"]),
                    "commission": _decimal_str(current["commission"]),
                    "nights": current["nights"],
                },
                "previous": {
                    "revenue": _decimal_str(previous["revenue"]),
                    "commission": _decimal_str(previous["commission"]),
                    "nights": previous["nights"],
                },
            }
        )

    return {
        "property_label": _property_label(tenant),
        "year": year,
        "comparison_year": comparison_year,
        "currency": currency,
        "months": months_payload,
    }
