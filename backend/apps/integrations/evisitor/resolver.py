from __future__ import annotations

from dataclasses import replace

from django.db.models import F, Q

from apps.integrations.evisitor.config import EvisitorRuntimeConfig
from apps.integrations.evisitor.exceptions import EvisitorConfigError
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property
from apps.tenants.models import Tenant


def resolve_evisitor_config(tenant: Tenant, property: Property | None) -> EvisitorRuntimeConfig:
    """
    Resolve active eVisitor credentials for a tenant/property pair.

    Precedence: property-specific IntegrationConfig, then tenant default (property=NULL).
    """
    filters = Q(property__isnull=True)
    if property is not None:
        filters |= Q(property=property)

    row = (
        IntegrationConfig.objects.filter(
            tenant=tenant,
            provider=IntegrationConfig.Provider.EVISITOR,
            is_active=True,
        )
        .filter(filters)
        .order_by(F("property_id").desc(nulls_last=True))
        .first()
    )
    if row is None:
        scope = property.slug if property else "tenant"
        raise EvisitorConfigError(
            f"Nema aktivne eVisitor IntegrationConfig za tenant={tenant.slug}, scope={scope}."
        )

    runtime = EvisitorRuntimeConfig.from_integration_dict(row.get_config_dict())
    if not runtime.enabled:
        raise EvisitorConfigError("eVisitor integracija nije uključena za ovaj objekt.")
    if property is not None:
        runtime = replace(
            runtime,
            default_stay_time_from=property.check_in_time.strftime("%H:%M"),
            default_stay_time_until=property.check_out_time.strftime("%H:%M"),
        )
    return runtime
