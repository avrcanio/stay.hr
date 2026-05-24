from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from apps.reservations.guest_slots import guests_for_checkout
from apps.reservations.models import Guest, Reservation
from apps.tourist_tax.models import (
    TouristTaxAccommodationCategory,
    TouristTaxAgeBracket,
    TouristTaxOrdinance,
    TouristTaxRate,
    TouristTaxSeason,
    TouristTaxZone,
)


class TouristTaxError(Exception):
    """Base error for tourist tax calculation."""


class TouristTaxValidationError(TouristTaxError):
    """Invalid input for tourist tax calculation."""


class TouristTaxConfigError(TouristTaxError):
    """Missing or incomplete tourist tax configuration."""


@dataclass(frozen=True)
class GuestAgeInput:
    date_of_birth: date | None = None
    age_years: int | None = None


@dataclass(frozen=True)
class TouristTaxGuestLine:
    guest_index: int
    age_years: int
    age_bracket_code: str
    multiplier: Decimal
    amount: Decimal


@dataclass(frozen=True)
class TouristTaxNightLine:
    night: date
    season_code: str
    base_rate: Decimal
    guest_lines: tuple[TouristTaxGuestLine, ...]
    night_total: Decimal


@dataclass(frozen=True)
class TouristTaxResult:
    nights: int
    total: Decimal
    currency: str
    lines: tuple[TouristTaxNightLine, ...]


def age_on(reference: date, dob: date) -> int:
    years = reference.year - dob.year
    if (reference.month, reference.day) < (dob.month, dob.day):
        years -= 1
    return years


def resolve_guest_age(guest: GuestAgeInput, *, reference: date) -> int:
    if guest.date_of_birth is not None:
        return age_on(reference, guest.date_of_birth)
    if guest.age_years is not None:
        return guest.age_years
    raise TouristTaxValidationError("Each guest must have date_of_birth or age_years.")


def date_in_season(day: date, season: TouristTaxSeason) -> bool:
    start = date(day.year, season.start_month, season.start_day)
    end = date(day.year, season.end_month, season.end_day)
    if start <= end:
        return start <= day <= end
    return day >= start or day <= end


def season_for_date(
    day: date,
    *,
    ordinance: TouristTaxOrdinance,
    seasons: list[TouristTaxSeason] | None = None,
) -> TouristTaxSeason:
    season_list = seasons or list(ordinance.seasons.all())
    for season in season_list:
        if date_in_season(day, season):
            return season
    raise TouristTaxConfigError(f"No season configured for date {day.isoformat()}.")


def age_bracket_for_age(
    age_years: int,
    *,
    ordinance: TouristTaxOrdinance,
    brackets: list[TouristTaxAgeBracket] | None = None,
) -> TouristTaxAgeBracket:
    bracket_list = brackets or list(ordinance.age_brackets.all())
    for bracket in sorted(bracket_list, key=lambda item: item.sort_order):
        if age_years < bracket.min_age:
            continue
        if bracket.max_age is not None and age_years > bracket.max_age:
            continue
        return bracket
    raise TouristTaxConfigError(f"No age bracket configured for age {age_years}.")


def _load_rate(
    *,
    zone: TouristTaxZone,
    season: TouristTaxSeason,
    category: TouristTaxAccommodationCategory,
    rate_cache: dict[tuple[int, int, int], TouristTaxRate],
) -> TouristTaxRate:
    key = (zone.pk, season.pk, category.pk)
    if key not in rate_cache:
        try:
            rate_cache[key] = TouristTaxRate.objects.get(
                zone=zone,
                season=season,
                category=category,
            )
        except TouristTaxRate.DoesNotExist as exc:
            raise TouristTaxConfigError(
                f"No rate for zone={zone.code}, season={season.code}, category={category.code}."
            ) from exc
    return rate_cache[key]


def calculate_tourist_tax(
    *,
    check_in: date,
    check_out: date,
    guests: list[GuestAgeInput],
    zone: TouristTaxZone,
    category: TouristTaxAccommodationCategory,
    ordinance: TouristTaxOrdinance | None = None,
) -> TouristTaxResult:
    """Calculate tourist tax per person per night.

    Nights are counted as [check_in, check_out) — the checkout day is not charged.
    Guest age is evaluated on check_in date.
    """
    if check_out <= check_in:
        raise TouristTaxValidationError("check_out must be after check_in.")
    if not guests:
        raise TouristTaxValidationError("At least one guest is required.")

    resolved_ordinance = ordinance or zone.ordinance
    seasons = list(resolved_ordinance.seasons.all())
    brackets = list(resolved_ordinance.age_brackets.all())
    guest_ages = [resolve_guest_age(guest, reference=check_in) for guest in guests]

    rate_cache: dict[tuple[int, int, int], TouristTaxRate] = {}
    night_lines: list[TouristTaxNightLine] = []
    total = Decimal("0.00")

    night = check_in
    while night < check_out:
        season = season_for_date(night, ordinance=resolved_ordinance, seasons=seasons)
        rate = _load_rate(
            zone=zone,
            season=season,
            category=category,
            rate_cache=rate_cache,
        )
        guest_lines: list[TouristTaxGuestLine] = []
        night_total = Decimal("0.00")

        for index, age_years in enumerate(guest_ages):
            bracket = age_bracket_for_age(
                age_years,
                ordinance=resolved_ordinance,
                brackets=brackets,
            )
            amount = (rate.amount * bracket.multiplier).quantize(Decimal("0.01"))
            guest_lines.append(
                TouristTaxGuestLine(
                    guest_index=index,
                    age_years=age_years,
                    age_bracket_code=bracket.code,
                    multiplier=bracket.multiplier,
                    amount=amount,
                )
            )
            night_total += amount

        night_lines.append(
            TouristTaxNightLine(
                night=night,
                season_code=season.code,
                base_rate=rate.amount,
                guest_lines=tuple(guest_lines),
                night_total=night_total,
            )
        )
        total += night_total
        night += timedelta(days=1)

    return TouristTaxResult(
        nights=len(night_lines),
        total=total.quantize(Decimal("0.01")),
        currency=resolved_ordinance.currency,
        lines=tuple(night_lines),
    )


def guests_from_reservation(reservation: Reservation) -> list[GuestAgeInput]:
    return [
        GuestAgeInput(date_of_birth=guest.date_of_birth)
        for guest in guests_for_checkout(reservation)
    ]


def calculate_tourist_tax_for_reservation(reservation: Reservation) -> TouristTaxResult:
    zone = reservation.property.tourist_tax_zone
    category = reservation.property.tourist_tax_category
    if zone is None or category is None:
        raise TouristTaxConfigError(
            "Property must have tourist_tax_zone and tourist_tax_category configured."
        )

    guests = guests_from_reservation(reservation)
    if not guests:
        raise TouristTaxValidationError("Reservation has no billable guests.")

    return calculate_tourist_tax(
        check_in=reservation.check_in,
        check_out=reservation.check_out,
        guests=guests,
        zone=zone,
        category=category,
    )
