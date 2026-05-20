from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.config import SmoobuRuntimeConfig
from apps.integrations.smoobu.mapping import UZORITA_SMOOBU_APARTMENTS
from apps.integrations.smoobu.resolver import get_active_smoobu_integration
from apps.properties.models import Property
from apps.tenants.models import Tenant

TEST_FERNET_KEY = "M8U_DJpQILQrKpxTOVtRrQp3nR0LJHAl2X0x-7JOH5k="


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class SmoobuIntegrationConfigTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
            default_language="hr",
        )
        self.prop = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
        )

    def test_encrypted_roundtrip_api_key_not_in_plaintext_column(self):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            property=self.prop,
            provider=IntegrationConfig.Provider.SMOOBU,
            is_active=True,
        )
        row.set_config_dict(
            {
                "api_base": "https://login.smoobu.com",
                "api_key": "rotated-secret-key",
                "apartments": [dict(UZORITA_SMOOBU_APARTMENTS[0])],
            }
        )
        row.save()

        row.refresh_from_db()
        self.assertEqual(row.config, {})
        self.assertTrue(row.config_encrypted)
        self.assertNotIn("rotated-secret-key", row.config_encrypted)

        decrypted = row.get_config_dict()
        self.assertEqual(decrypted["api_key"], "rotated-secret-key")
        runtime = SmoobuRuntimeConfig.from_integration_dict(decrypted)
        self.assertEqual(runtime.api_key, "rotated-secret-key")
        self.assertEqual(runtime.apartment_id_for_unit_code("R1"), 3327457)

    def test_get_active_smoobu_integration_finds_property_scoped_config(self):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            property=self.prop,
            provider=IntegrationConfig.Provider.SMOOBU,
            is_active=True,
        )
        row.set_config_dict(
            {
                "api_key": "test-key",
                "apartments": [dict(UZORITA_SMOOBU_APARTMENTS[0])],
            }
        )
        row.save()

        resolved = get_active_smoobu_integration(self.tenant.slug)
        self.assertEqual(resolved.pk, row.pk)

    @patch("apps.integrations.smoobu.verify.verify_smoobu_api_key")
    def test_seed_command_stores_encrypted_config(self, mock_verify):
        mock_verify.return_value = {"id": 1, "email": "test@example.com"}
        from django.core.management import call_command

        call_command(
            "seed_uzorita_smoobu_config",
            api_key="new-key-from-env",
            verbosity=0,
        )

        row = IntegrationConfig.objects.get(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.SMOOBU,
            property=self.prop,
        )
        self.assertEqual(row.config, {})
        self.assertEqual(row.get_config_dict()["api_key"], "new-key-from-env")
        mock_verify.assert_called_once_with("new-key-from-env")
