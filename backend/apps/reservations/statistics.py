"""Mjesečne agregacije prihoda, provizije i noći za recepcijsku statistiku."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.reservations.models import MonthlyStatisticsOverride, Reservation

DEFAULT_CURRENCY = "EUR"

_REALIZED_STATUSES = [
    Reservation.Status.CHECKED_IN,
    Reservation.Status.CHECKED_OUT,
]
_RESERVED_STATUSES = [
    Reservation.Status.EXPECTED,
    Reservation.Status.CHECKED_IN,
    Reservation.Status.CHECKED_OUT,
]


def _property_label(tenant) -> str:
    return tenant.name


def _realized_queryset(tenant, year: int):
    comparison_year = year - 1
    prior_year = year - 2
    return (
        Reservation.objects.for_tenant(tenant)
        .filter(
            status__in=_REALIZED_STATUSES,
            check_in__gte=date(prior_year, 1, 1),
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


def _reserved_queryset(tenant, year: int):
    """Sve aktivne rezervacije (bez canceled) za tekuću godinu — bookirano po check-in mjesecu."""
    return (
        Reservation.objects.for_tenant(tenant)
        .filter(
            status__in=_RESERVED_STATUSES,
            check_in__gte=date(year, 1, 1),
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


def _canceled_queryset(tenant, year: int):
    return (
        Reservation.objects.for_tenant(tenant)
        .filter(
            status=Reservation.Status.CANCELED,
            check_in__gte=date(year, 1, 1),
            check_in__lte=date(year, 12, 31),
        )
        .only(
            "check_in",
            "check_out",
            "amount",
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


def _empty_current_bucket() -> dict:
    return {
        "revenue": Decimal("0"),
        "commission": Decimal("0"),
        "nights": 0,
        "reserved_revenue": Decimal("0"),
        "reserved_commission": Decimal("0"),
        "reserved_nights": 0,
        "canceled_revenue": Decimal("0"),
        "canceled_nights": 0,
    }


def _empty_previous_bucket() -> dict:
    return {
        "revenue": Decimal("0"),
        "commission": Decimal("0"),
        "nights": 0,
        "prior_revenue": Decimal("0"),
        "prior_nights": 0,
        "canceled_revenue": Decimal("0"),
        "canceled_nights": 0,
    }


def aggregate_monthly_statistics(tenant, year: int) -> dict:
    comparison_year = year - 1
    prior_year = year - 2
    buckets: dict[int, dict[str, dict]] = {
        month: {
            "current": _empty_current_bucket(),
            "previous": _empty_previous_bucket(),
        }
        for month in range(1, 13)
    }

    currency = DEFAULT_CURRENCY
    for reservation in _realized_queryset(tenant, year).iterator():
        check_in = reservation.check_in
        if check_in is None:
            continue
        y = check_in.year
        month = check_in.month
        if y == year:
            slot = buckets[month]["current"]
        elif y == comparison_year:
            slot = buckets[month]["previous"]
        elif y == prior_year:
            slot = buckets[month]["previous"]
            slot["prior_revenue"] += reservation.amount or Decimal("0")
            slot["prior_nights"] += _effective_nights(reservation)
            if reservation.currency:
                currency = reservation.currency
            continue
        else:
            continue

        slot["revenue"] += reservation.amount or Decimal("0")
        slot["commission"] += reservation.commission_amount or Decimal("0")
        slot["nights"] += _effective_nights(reservation)
        if reservation.currency:
            currency = reservation.currency

    for reservation in _reserved_queryset(tenant, year).iterator():
        check_in = reservation.check_in
        if check_in is None:
            continue
        month = check_in.month
        slot = buckets[month]["current"]
        slot["reserved_revenue"] += reservation.amount or Decimal("0")
        slot["reserved_commission"] += reservation.commission_amount or Decimal("0")
        slot["reserved_nights"] += _effective_nights(reservation)
        if reservation.currency:
            currency = reservation.currency

    for reservation in _canceled_queryset(tenant, year).iterator():
        check_in = reservation.check_in
        if check_in is None:
            continue
        month = check_in.month
        slot = buckets[month]["current"]
        slot["canceled_revenue"] += reservation.amount or Decimal("0")
        slot["canceled_nights"] += _effective_nights(reservation)
        if reservation.currency:
            currency = reservation.currency

    for reservation in _canceled_queryset(tenant, comparison_year).iterator():
        check_in = reservation.check_in
        if check_in is None:
            continue
        month = check_in.month
        slot = buckets[month]["previous"]
        slot["canceled_revenue"] += reservation.amount or Decimal("0")
        slot["canceled_nights"] += _effective_nights(reservation)
        if reservation.currency:
            currency = reservation.currency

    overrides = {
        (row.year, row.month): row
        for row in MonthlyStatisticsOverride.objects.for_tenant(tenant).filter(
            year__in=[year, comparison_year, prior_year],
        )
    }
    for month in range(1, 13):
        override = overrides.get((year, month))
        if override is not None:
            slot = buckets[month]["current"]
            slot["revenue"] = override.revenue
            slot["commission"] = override.commission or Decimal("0")
            slot["nights"] = override.nights
            if override.currency:
                currency = override.currency

        override = overrides.get((comparison_year, month))
        if override is not None:
            slot = buckets[month]["previous"]
            slot["revenue"] = override.revenue
            slot["commission"] = override.commission or Decimal("0")
            slot["nights"] = override.nights
            if override.currency:
                currency = override.currency

        override = overrides.get((prior_year, month))
        if override is not None:
            slot = buckets[month]["previous"]
            slot["prior_revenue"] = override.revenue
            slot["prior_nights"] = override.nights
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
                    "reserved_revenue": _decimal_str(current["reserved_revenue"]),
                    "reserved_commission": _decimal_str(current["reserved_commission"]),
                    "reserved_nights": current["reserved_nights"],
                    "canceled_revenue": _decimal_str(current["canceled_revenue"]),
                    "canceled_nights": current["canceled_nights"],
                },
                "previous": {
                    "revenue": _decimal_str(previous["revenue"]),
                    "commission": _decimal_str(previous["commission"]),
                    "nights": previous["nights"],
                    "prior_revenue": _decimal_str(previous["prior_revenue"]),
                    "prior_nights": previous["prior_nights"],
                    "canceled_revenue": _decimal_str(previous["canceled_revenue"]),
                    "canceled_nights": previous["canceled_nights"],
                },
            }
        )

    return {
        "property_label": _property_label(tenant),
        "year": year,
        "comparison_year": comparison_year,
        "prior_year": prior_year,
        "currency": currency,
        "months": months_payload,
    }
