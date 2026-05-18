import hashlib
from datetime import date

from apps.reservations.models import Reservation

LEGACY_DB_ALIAS = "uzorita_legacy"

BOOKING_TO_OPERATIONAL = {
    "pending": Reservation.Status.EXPECTED,
    "confirmed": Reservation.Status.EXPECTED,
    "cancelled": Reservation.Status.CANCELED,
    "canceled": Reservation.Status.CANCELED,
}

UZORITA_OPERATIONAL = frozenset(
    {
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CHECKED_OUT,
        Reservation.Status.CANCELED,
    }
)

INVALID_OPERATIONAL_AFTER_MIGRATE = frozenset({"pending", "confirmed", "cancelled"})


def map_legacy_status(raw_status: str) -> str:
    value = (raw_status or "").strip()
    if value in BOOKING_TO_OPERATIONAL:
        return BOOKING_TO_OPERATIONAL[value]
    if value in UZORITA_OPERATIONAL:
        return value
    return Reservation.Status.EXPECTED


def reservation_fingerprint(check_in: date, status: str, guest_count: int) -> str:
    payload = f"{check_in.isoformat()}|{status}|{guest_count}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def i18n_pick(data: dict | None, lang: str = "hr") -> str:
    if not isinstance(data, dict):
        return ""
    for key in (lang, lang.split("-", 1)[0], "en"):
        val = data.get(key)
        if val:
            return str(val)
    for val in data.values():
        if val:
            return str(val)
    return ""
