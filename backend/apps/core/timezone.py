from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

DEFAULT_TIMEZONE = "Europe/Zagreb"


def effective_timezone(*, property: Property | None = None, tenant: Tenant | None = None) -> str:
    if property is not None and (property.timezone or "").strip():
        return property.timezone.strip()
    if tenant is not None and (tenant.timezone or "").strip():
        return tenant.timezone.strip()
    return DEFAULT_TIMEZONE


def property_local_now(property: Property) -> datetime:
    tz = ZoneInfo(effective_timezone(property=property, tenant=property.tenant))
    return datetime.now(tz)


def tenant_local_now(tenant: Tenant) -> datetime:
    tz = ZoneInfo(effective_timezone(tenant=tenant))
    return datetime.now(tz)


def reservation_check_in_datetime(reservation: Reservation) -> datetime:
    """Property check-in time on reservation.check_in date (property-local TZ)."""
    prop = reservation.property
    tz = ZoneInfo(effective_timezone(property=prop, tenant=reservation.tenant))
    return datetime.combine(reservation.check_in, prop.check_in_time, tzinfo=tz)


def effective_guest_stated_arrival_at(reservation: Reservation) -> datetime:
    """Guest-stated arrival or property default check-in time when not stated."""
    if reservation.guest_stated_arrival_at is not None:
        return reservation.guest_stated_arrival_at
    return reservation_check_in_datetime(reservation)
