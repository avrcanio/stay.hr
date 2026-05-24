from __future__ import annotations

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from apps.integrations.channex.ari_service import get_active_channex_integration
from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property
from apps.tenants.models import Tenant

TEST_FERNET_KEY = "M8U_DJpQILQrKpxTOVtRrQp3nR0LJHAl2X0x-7JOH5k="


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class ChannexIntegrationConfigTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="demo",
            name="Demo",
            timezone="Europe/Zagreb",
            default_language="hr",
        )
        self.prop = Property.objects.create(
            tenant=self.tenant,
            slug="channex-demo",
            name="Channex Demo",
        )

    def test_encrypted_roundtrip_api_key_not_in_plaintext_column(self):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            property=self.prop,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        row.set_config_dict(
            {
                "api_key": "channex-secret-key",
                "webhook_secret": "channex-webhook-secret",
                "property_id": "e00e6034-c154-4754-b5d9-9fff73ad12f6",
                "room_types": [
                    {
                        "unit_code": "R1",
                        "channex_room_type_id": "rt-1",
                        "channex_title": "Room 1",
                    }
                ],
            }
        )
        row.save()

        row.refresh_from_db()
        self.assertEqual(row.config, {})
        self.assertTrue(row.config_encrypted)
        self.assertNotIn("channex-secret-key", row.config_encrypted)
        self.assertNotIn("channex-webhook-secret", row.config_encrypted)

        decrypted = row.get_config_dict()
        self.assertEqual(decrypted["api_key"], "channex-secret-key")
        runtime = ChannexRuntimeConfig.from_integration_dict(decrypted)
        self.assertEqual(runtime.api_key, "channex-secret-key")
        self.assertEqual(runtime.property_id, "e00e6034-c154-4754-b5d9-9fff73ad12f6")
        self.assertEqual(runtime.room_type_id_for_unit_code("R1"), "rt-1")

    @patch.dict(
        os.environ,
        {
            "CHANNEX_API_KEY": "env-api-key",
            "CHANNEX_WEBHOOK_SECRET": "env-webhook-secret",
            "CHANNEX_PROPERTY_ID": "env-property-id",
        },
        clear=False,
    )
    def test_runtime_config_env_fallback(self):
        runtime = ChannexRuntimeConfig.from_integration_dict({})
        self.assertEqual(runtime.api_key, "env-api-key")
        self.assertEqual(runtime.webhook_secret, "env-webhook-secret")
        self.assertEqual(runtime.property_id, "env-property-id")
        self.assertEqual(runtime.base_url, "https://staging.channex.io/api/v1")

    @patch.dict(
        os.environ,
        {
            "CHANNEX_API_KEY": "env-api-key",
            "CHANNEX_WEBHOOK_SECRET": "env-webhook-secret",
            "CHANNEX_PROPERTY_ID": "env-property-id",
        },
        clear=False,
    )
    def test_sync_credentials_command_merges_env(self):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            property=self.prop,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        existing_room_types = [
            {
                "unit_code": "R1",
                "channex_room_type_id": "rt-1",
                "channex_title": "Room 1",
            }
        ]
        row.set_config_dict(
            {
                "api_key": "old-key",
                "property_id": "old-property-id",
                "room_types": existing_room_types,
                "booking_test_rooms": [{"unit_code": "R1", "channex_room_type_id": "rt-1"}],
            }
        )
        row.save()

        call_command("sync_channex_credentials", pk=row.pk, verbosity=0)

        row.refresh_from_db()
        config = row.get_config_dict()
        self.assertEqual(config["api_key"], "env-api-key")
        self.assertEqual(config["webhook_secret"], "env-webhook-secret")
        self.assertEqual(config["property_id"], "env-property-id")
        self.assertEqual(config["room_types"], existing_room_types)
        self.assertEqual(
            config["booking_test_rooms"],
            [{"unit_code": "R1", "channex_room_type_id": "rt-1"}],
        )

    def test_get_active_channex_integration_finds_property_scoped_config(self):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            property=self.prop,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        row.set_config_dict(
            {
                "api_key": "test-key",
                "property_id": "prop-uuid",
                "room_types": [{"unit_code": "R1", "channex_room_type_id": "rt-1"}],
            }
        )
        row.save()

        resolved = get_active_channex_integration(self.tenant.slug)
        self.assertEqual(resolved.pk, row.pk)


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class IntegrationConfigAdminSiteTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="demo", name="Demo")
        self.prop = Property.objects.create(
            tenant=self.tenant,
            slug="channex-demo",
            name="Channex Demo",
        )
        self.row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            property=self.prop,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.row.set_config_dict(
            {
                "api_key": "ch-key",
                "webhook_secret": "wh-secret",
                "property_id": "e00e6034-c154-4754-b5d9-9fff73ad12f6",
                "environment": "staging",
                "room_types": [{"unit_code": "R1", "channex_room_type_id": "rt-1"}],
            }
        )
        self.row.save()

        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="admin-channex-test",
            email="admin-channex-test@stay.hr",
            password="test-pass",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_channex_change_page_returns_200(self):
        response = self.client.get(
            f"/admin/integrations/integrationconfig/{self.row.pk}/change/",
            HTTP_HOST="admin.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("id_property_id", html)
        self.assertIn("id_api_key", html)
        self.assertIn("Credentials status", html)
