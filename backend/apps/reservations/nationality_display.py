"""ISO2 country code for reservation/guest display (flags in Hospira)."""

from __future__ import annotations

from apps.reservations.models import Guest, Reservation

_ISO3_TO_ISO2 = {"HRV": "HR", "DEU": "DE", "AUT": "AT", "POL": "PL"}


def normalize_country_iso2(raw: str) -> str:
    value = (raw or "").strip().upper()
    if not value:
        return ""
    if len(value) == 3:
        return _ISO3_TO_ISO2.get(value, value[:2])
    return value[:2]


def guest_nationality_iso2(guest: Guest) -> str:
    for field in (guest.nationality, guest.document_country_iso2):
        iso2 = normalize_country_iso2(str(field or ""))
        if iso2:
            return iso2
    return ""


def reservation_nationality_iso2(reservation: Reservation) -> str:
    primary = next((g for g in reservation.guests.all() if g.is_primary), None)
    if primary:
        iso2 = guest_nationality_iso2(primary)
        if iso2:
            return iso2
    for guest in reservation.guests.all():
        iso2 = guest_nationality_iso2(guest)
        if iso2:
            return iso2
    return normalize_country_iso2(reservation.booker_country)
