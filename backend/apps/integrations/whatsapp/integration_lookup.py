from __future__ import annotations

from apps.integrations.models import IntegrationConfig
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.tenants.constants import PLATFORM_TENANT_SLUG
from apps.tenants.models import Tenant


def get_platform_tenant() -> Tenant | None:
    return Tenant.objects.filter(slug=PLATFORM_TENANT_SLUG, is_system=True).first()


def _runtime_from_row(row: IntegrationConfig) -> WhatsAppRuntimeConfig:
    return WhatsAppRuntimeConfig.from_integration_dict(row.get_config_dict())


def get_active_whatsapp_integration(
    tenant: Tenant,
) -> tuple[IntegrationConfig | None, WhatsAppRuntimeConfig | None]:
    """Return active WhatsApp config for a specific tenant (no platform fallback)."""
    row = (
        IntegrationConfig.objects.filter(
            tenant=tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            is_active=True,
            property__isnull=True,
        )
        .order_by("pk")
        .first()
    )
    if row is None:
        return None, None
    return row, _runtime_from_row(row)


def get_platform_whatsapp_integration() -> tuple[IntegrationConfig | None, WhatsAppRuntimeConfig | None]:
    platform = get_platform_tenant()
    if platform is None:
        return None, None
    row = (
        IntegrationConfig.objects.filter(
            tenant=platform,
            provider=IntegrationConfig.Provider.WHATSAPP,
            is_active=True,
        )
        .order_by("-is_platform_default", "pk")
        .first()
    )
    if row is None:
        return None, None
    return row, _runtime_from_row(row)


def resolve_whatsapp_integration(
    tenant: Tenant,
) -> tuple[IntegrationConfig | None, WhatsAppRuntimeConfig | None]:
    """Resolve outbound WhatsApp config: tenant config first, then platform fallback."""
    if tenant.slug != PLATFORM_TENANT_SLUG:
        row, runtime = get_active_whatsapp_integration(tenant)
        if row is not None and runtime is not None and runtime.phone_number_id:
            return row, runtime
    return get_platform_whatsapp_integration()
