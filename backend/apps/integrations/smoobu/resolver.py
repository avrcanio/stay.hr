from __future__ import annotations

from django.db.models import F, Q

from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.config import SmoobuRuntimeConfig
from apps.integrations.smoobu.exceptions import SmoobuConfigError
from apps.properties.models import Property
from apps.tenants.models import Tenant


def _smoobu_config_queryset(tenant: Tenant, property: Property | None):
    qs = IntegrationConfig.objects.filter(
        tenant=tenant,
        provider=IntegrationConfig.Provider.SMOOBU,
        is_active=True,
    )
    if property is not None:
        qs = qs.filter(Q(property__isnull=True) | Q(property=property))
    return qs.order_by(F("property_id").desc(nulls_last=True))


def resolve_smoobu_config(tenant: Tenant, property: Property | None) -> SmoobuRuntimeConfig:
    row = _smoobu_config_queryset(tenant, property).first()
    if row is None:
        scope = property.slug if property else "tenant"
        raise SmoobuConfigError(
            f"Nema aktivne Smoobu IntegrationConfig za tenant={tenant.slug}, scope={scope}."
        )

    runtime = SmoobuRuntimeConfig.from_integration_dict(row.get_config_dict())
    if not runtime.api_key:
        raise SmoobuConfigError("Smoobu api_key nije postavljen (config ili SMOOBU_API_KEY).")
    if not runtime.apartments:
        raise SmoobuConfigError("Smoobu apartments mapping je prazan.")
    return runtime


def get_active_smoobu_integration(
    tenant_slug: str,
    *,
    property: Property | None = None,
) -> IntegrationConfig:
    tenant = Tenant.objects.filter(slug=tenant_slug).first()
    if tenant is None:
        raise SmoobuConfigError(f"Tenant not found: {tenant_slug}")

    row = (
        _smoobu_config_queryset(tenant, property)
        .select_related("tenant", "property")
        .first()
    )
    if row is None:
        scope = property.slug if property else "tenant"
        raise SmoobuConfigError(
            f"No Smoobu config for tenant={tenant_slug}, scope={scope}."
        )
    return row
