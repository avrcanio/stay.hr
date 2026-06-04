from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apps.properties.models import Property
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
