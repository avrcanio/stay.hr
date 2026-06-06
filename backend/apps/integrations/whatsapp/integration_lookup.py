from __future__ import annotations

from apps.integrations.models import IntegrationConfig
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.tenants.models import Tenant


def get_active_whatsapp_integration(
    tenant: Tenant,
) -> tuple[IntegrationConfig | None, WhatsAppRuntimeConfig | None]:
    row = (
        IntegrationConfig.objects.filter(
            tenant=tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            is_active=True,
        )
        .order_by("pk")
        .first()
    )
    if row is None:
        return None, None
    runtime = WhatsAppRuntimeConfig.from_integration_dict(row.get_config_dict())
    return row, runtime
