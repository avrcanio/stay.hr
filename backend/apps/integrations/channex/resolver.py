from __future__ import annotations

from django.db.models import F, Q

from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.channex.exceptions import ChannexConfigError
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property
from apps.tenants.models import Tenant


def resolve_channex_config(tenant: Tenant, property: Property | None) -> ChannexRuntimeConfig:
    filters = Q(property__isnull=True)
    if property is not None:
        filters |= Q(property=property)

    row = (
        IntegrationConfig.objects.filter(
            tenant=tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        .filter(filters)
        .order_by(F("property_id").desc(nulls_last=True))
        .first()
    )
    if row is None:
        scope = property.slug if property else "tenant"
        raise ChannexConfigError(
            f"Nema aktivne Channex IntegrationConfig za tenant={tenant.slug}, scope={scope}."
        )

    runtime = ChannexRuntimeConfig.from_integration_dict(row.get_config_dict())
    if not runtime.property_id:
        raise ChannexConfigError("Channex property_id nije postavljen u IntegrationConfig.")
    if not runtime.api_key:
        raise ChannexConfigError("Channex api_key nije postavljen (config ili CHANNEX_API_KEY).")
    if not runtime.room_types:
        raise ChannexConfigError("Channex room_types mapping je prazan.")
    return runtime
