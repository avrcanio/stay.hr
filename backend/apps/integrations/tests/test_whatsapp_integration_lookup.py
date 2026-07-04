from django.test import TestCase, override_settings

from apps.integrations.models import IntegrationConfig
from apps.integrations.whatsapp.integration_lookup import (
    get_platform_whatsapp_integration,
    resolve_whatsapp_integration,
)
from apps.tenants.constants import PLATFORM_TENANT_SLUG
from apps.tenants.models import Tenant

TEST_FERNET_KEY = "M8U_DJpQILQrKpxTOVtRrQp3nR0LJHAl2X0x-7JOH5k="


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY, WHATSAPP_ACCESS_TOKEN="tok")
class WhatsAppIntegrationLookupTests(TestCase):
    def setUp(self):
        self.platform, _ = Tenant.objects.get_or_create(
            slug=PLATFORM_TENANT_SLUG,
            defaults={"name": "Platform", "is_system": True},
        )
        self.hotel = Tenant.objects.create(slug="uzorita-lookup", name="Uzorita")
        self.platform_cfg, _ = IntegrationConfig.objects.update_or_create(
            tenant=self.platform,
            provider=IntegrationConfig.Provider.WHATSAPP,
            property=None,
            defaults={
                "routing_key": "platform-pnid-lookup",
                "is_active": True,
                "is_platform_default": True,
            },
        )
        self.platform_cfg.set_config_dict(
            {
                "phone_number_id": "platform-pnid-lookup",
                "display_phone_number": "+385976615439",
            }
        )
        self.platform_cfg.save()

    def test_resolve_uses_tenant_config_when_present(self):
        tenant_cfg = IntegrationConfig.objects.create(
            tenant=self.hotel,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key="hotel-pnid",
            is_active=True,
        )
        tenant_cfg.set_config_dict({"phone_number_id": "hotel-pnid"})
        tenant_cfg.save()

        row, runtime = resolve_whatsapp_integration(self.hotel)
        self.assertEqual(row.pk, tenant_cfg.pk)
        self.assertEqual(runtime.phone_number_id, "hotel-pnid")

    def test_resolve_falls_back_to_platform(self):
        row, runtime = resolve_whatsapp_integration(self.hotel)
        self.assertEqual(row.pk, self.platform_cfg.pk)
        self.assertEqual(runtime.phone_number_id, "platform-pnid-lookup")

    def test_get_platform_whatsapp_integration(self):
        row, runtime = get_platform_whatsapp_integration()
        self.assertEqual(row.pk, self.platform_cfg.pk)
