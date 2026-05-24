from __future__ import annotations

from apps.integrations.models import IntegrationConfig


def find_whatsapp_integration(phone_number_id: str) -> IntegrationConfig | None:
    routing_key = (phone_number_id or "").strip()
    if not routing_key:
        return None
    return (
        IntegrationConfig.objects.filter(
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key=routing_key,
            is_active=True,
        )
        .select_related("tenant", "property")
        .first()
    )
