"""ISO2 country code for reservation/guest display (flags in Hospira)."""

from __future__ import annotations

from apps.reservations.models import Guest, Reservation

# Mirror of apps.integrations.evisitor.lookups._ISO2_FALLBACKS (ISO2 → ISO3).
_ISO2_TO_ISO3 = {
    "HR": "HRV",
    "DE": "DEU",
    "IT": "ITA",
    "AT": "AUT",
    "SI": "SVN",
    "BE": "BEL",
    "FR": "FRA",
    "NL": "NLD",
    "GB": "GBR",
    "US": "USA",
    "CH": "CHE",
    "PL": "POL",
    "CZ": "CZE",
    "SK": "SVK",
    "HU": "HUN",
    "RS": "SRB",
    "BA": "BIH",
    "ME": "MNE",
    "MK": "MKD",
    "AL": "ALB",
    "GR": "GRC",
    "ES": "ESP",
    "PT": "PRT",
    "SE": "SWE",
    "NO": "NOR",
    "DK": "DNK",
    "FI": "FIN",
    "IE": "IRL",
    "LU": "LUX",
    "IN": "IND",
    "CO": "COL",
    "RO": "ROU",
    "TR": "TUR",
    "UA": "UKR",
    "LT": "LTU",
    "LV": "LVA",
    "BR": "BRA",
    "CA": "CAN",
    "AR": "ARG",
    "AU": "AUS",
    "CL": "CHL",
    "CN": "CHN",
    "IL": "ISR",
    "JP": "JPN",
    "KR": "KOR",
    "MT": "MLT",
    "TH": "THA",
    "TW": "TWN",
    "CY": "CYP",
}

_ISO3_TO_ISO2 = {iso3: iso2 for iso2, iso3 in _ISO2_TO_ISO3.items()}
_KNOWN_ISO2 = frozenset(_ISO2_TO_ISO3)

# Truncated / invalid ISO2 codes that should fall through to document ISO3.
_INVALID_ISO2 = frozenset({"PO"})


def iso3_to_iso2(iso3: str) -> str:
    value = (iso3 or "").strip().upper()
    if len(value) != 3:
        return ""
    return _ISO3_TO_ISO2.get(value, "")


def normalize_country_iso2(raw: str) -> str:
    value = (raw or "").strip().upper()
    if not value:
        return ""
    if len(value) == 3:
        return iso3_to_iso2(value)
    if len(value) == 2:
        if value in _INVALID_ISO2:
            return ""
        if value in _KNOWN_ISO2 or value.isalpha():
            return value
    return ""


def guest_nationality_iso2(guest: Guest) -> str:
    for field in (guest.nationality, guest.document_country_iso2):
        iso2 = normalize_country_iso2(str(field or ""))
        if iso2:
            return iso2
    iso2_from_iso3 = iso3_to_iso2(str(guest.document_country_iso3 or ""))
    if iso2_from_iso3:
        return iso2_from_iso3
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
