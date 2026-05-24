from django.test import TestCase

from apps.integrations.channel_manager.resolver import (
    ChannelManagerConfigError,
    get_channel_manager,
    require_channex,
    require_smoobu,
    validate_channel_manager_integration,
)
from apps.integrations.models import IntegrationConfig
from apps.tenants.models import ChannelManager, Tenant, TenantReceptionSettings


class ChannelManagerResolverTests(TestCase):
    def setUp(self):
        self.demo = Tenant.objects.create(slug="demo", name="Demo")
        self.uzorita = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.other = Tenant.objects.create(slug="other", name="Other")

        TenantReceptionSettings.objects.create(
            tenant=self.demo,
            channel_manager=ChannelManager.CHANNEX,
        )
        TenantReceptionSettings.objects.create(
            tenant=self.uzorita,
            channel_manager=ChannelManager.SMOOBU,
        )

    def test_get_channel_manager_from_settings(self):
        self.assertEqual(get_channel_manager(self.demo), ChannelManager.CHANNEX)
        self.assertEqual(get_channel_manager(self.uzorita), ChannelManager.SMOOBU)

    def test_get_channel_manager_defaults_to_none(self):
        self.assertEqual(get_channel_manager(self.other), ChannelManager.NONE)

    def test_require_channex_raises_for_smoobu(self):
        with self.assertRaises(ChannelManagerConfigError):
            require_channex(self.uzorita)

    def test_require_smoobu_raises_for_channex(self):
        with self.assertRaises(ChannelManagerConfigError):
            require_smoobu(self.demo)

    def test_validate_channex_requires_active_config(self):
        settings_row = TenantReceptionSettings.objects.get(tenant=self.demo)
        with self.assertRaises(ChannelManagerConfigError):
            validate_channel_manager_integration(settings_row)

        IntegrationConfig.objects.create(
            tenant=self.demo,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        validate_channel_manager_integration(settings_row)

    def test_validate_smoobu_requires_active_config(self):
        settings_row = TenantReceptionSettings.objects.get(tenant=self.uzorita)
        with self.assertRaises(ChannelManagerConfigError):
            validate_channel_manager_integration(settings_row)

        IntegrationConfig.objects.create(
            tenant=self.uzorita,
            provider=IntegrationConfig.Provider.SMOOBU,
            is_active=True,
        )
        validate_channel_manager_integration(settings_row)
