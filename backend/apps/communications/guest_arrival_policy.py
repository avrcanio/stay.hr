"""Evaluate guest arrival time against property window."""

from __future__ import annotations

from datetime import datetime, time
from typing import Literal

from apps.properties.models import AfterHoursArrivalPolicy, Property
from apps.reservations.models import Reservation

ArrivalWindowStatus = Literal["within", "late", "no_limit", "before_earliest"]


def format_time_hm(value: time | None) -> str:
    if value is None:
        return ""
    return value.strftime("%H:%M")


def after_hours_contact_phone(property: Property) -> str:
    direct = (property.after_hours_contact_phone or "").strip()
    if direct:
        return direct
    contact = property.contact if isinstance(property.contact, dict) else {}
    for key in ("phone", "mobile", "reception_phone", "whatsapp"):
        val = str(contact.get(key) or "").strip()
        if val:
            return val
    return ""


def arrival_window_times(property: Property) -> tuple[time, time | None]:
    return property.check_in_time, property.check_in_latest_time


def _time_on_check_in(reservation: Reservation, parsed: datetime) -> time:
    return parsed.timetz().replace(tzinfo=None)


def evaluate_arrival_time(
    reservation: Reservation,
    parsed: datetime | None,
) -> ArrivalWindowStatus:
    if parsed is None:
        return "no_limit"
    prop = reservation.property
    earliest, latest = arrival_window_times(prop)
    stated = _time_on_check_in(reservation, parsed)
    if stated < earliest:
        return "before_earliest"
    if latest is None:
        return "no_limit"
    if stated > latest:
        return "late"
    return "within"


def is_late_arrival(reservation: Reservation, parsed: datetime | None) -> bool:
    return evaluate_arrival_time(reservation, parsed) == "late"


def is_after_hours_not_allowed(property: Property) -> bool:
    return property.after_hours_arrival_policy == AfterHoursArrivalPolicy.NOT_ALLOWED
