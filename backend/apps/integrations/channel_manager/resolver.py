from __future__ import annotations

from apps.integrations.models import IntegrationConfig
from apps.tenants.models import ChannelManager, Tenant, TenantReceptionSettings


class ChannelManagerConfigError(Exception):
    pass


def get_channel_manager(tenant: Tenant) -> str:
    settings = TenantReceptionSettings.objects.filter(tenant_id=tenant.pk).first()
    if settings is None:
        return ChannelManager.NONE
    return settings.channel_manager or ChannelManager.NONE


def _require_manager(tenant: Tenant, expected: str) -> None:
    manager = get_channel_manager(tenant)
    if manager != expected:
        label = dict(ChannelManager.choices).get(expected, expected)
        raise ChannelManagerConfigError(
            f"Tenant channel_manager is '{manager}', expected '{label}'."
        )


def require_channex(tenant: Tenant) -> None:
    _require_manager(tenant, ChannelManager.CHANNEX)


def validate_channel_manager_integration(settings_row: TenantReceptionSettings) -> None:
    """Ensure active IntegrationConfig exists when channel_manager requires it."""
    manager = settings_row.channel_manager
    tenant = settings_row.tenant
    if manager == ChannelManager.CHANNEX:
        has_config = IntegrationConfig.objects.filter(
            tenant=tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        ).exists()
        if not has_config:
            raise ChannelManagerConfigError(
                "channel_manager=channex requires an active Channex IntegrationConfig."
            )
