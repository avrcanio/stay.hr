from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.integrations.admin.forms import IntegrationConfigAdminForm
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property
from apps.tenants.models import Tenant

TEST_FERNET_KEY = "M8U_DJpQILQrKpxTOVtRrQp3nR0LJHAl2X0x-7JOH5k="


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class IntegrationConfigAdminFormTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.prop = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
        )

    def _create_channex_row(
        self,
        *,
        api_key: str = "ch-key",
        webhook_secret: str = "wh-secret",
        property_id: str = "prop-uuid",
    ) -> IntegrationConfig:
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        row.set_config_dict(
            {
                "api_key": api_key,
                "webhook_secret": webhook_secret,
                "property_id": property_id,
                "room_types": [{"unit_code": "R1", "channex_room_type_id": "rt-1"}],
            }
        )
        row.save()
        return row

    def _channex_form_data(self, row: IntegrationConfig, **overrides):
        data = {
            "tenant": self.tenant.pk,
            "property": "",
            "provider": IntegrationConfig.Provider.CHANNEX,
            "routing_key": "",
            "is_active": True,
            "api_key": "",
            "webhook_secret": "",
            "environment": "staging",
            "base_url": "",
            "property_id": row.get_config_dict().get("property_id", ""),
            "sync_property_slug": "",
            "certification_property_slug": "",
            "use_generated_ari": False,
            "room_types_json": "",
            "booking_test_rooms_json": "",
        }
        data.update(overrides)
        return data

    def test_channex_blank_api_key_keeps_existing(self):
        row = self._create_channex_row(api_key="original-ch-key")
        form = IntegrationConfigAdminForm(
            data=self._channex_form_data(row, api_key=""),
            instance=row,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.get_config_dict()["api_key"], "original-ch-key")

    def test_channex_new_api_key_overwrites(self):
        row = self._create_channex_row(api_key="original-ch-key")
        form = IntegrationConfigAdminForm(
            data=self._channex_form_data(row, api_key="rotated-ch-key"),
            instance=row,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.get_config_dict()["api_key"], "rotated-ch-key")

    def test_channex_webhook_secret_blank_keeps_existing(self):
        row = self._create_channex_row()
        form = IntegrationConfigAdminForm(
            data=self._channex_form_data(row, api_key="", webhook_secret=""),
            instance=row,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        config = saved.get_config_dict()
        self.assertEqual(config["api_key"], "ch-key")
        self.assertEqual(config["webhook_secret"], "wh-secret")

    def test_channex_webhook_secret_overwrite(self):
        row = self._create_channex_row(webhook_secret="old-secret")
        form = IntegrationConfigAdminForm(
            data=self._channex_form_data(row, webhook_secret="new-secret", property_id=""),
            instance=row,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.get_config_dict()["webhook_secret"], "new-secret")

    def test_channex_property_id_persisted(self):
        row = self._create_channex_row(property_id="old-property-id")
        form = IntegrationConfigAdminForm(
            data=self._channex_form_data(
                row,
                property_id="e00e6034-c154-4754-b5d9-9fff73ad12f6",
            ),
            instance=row,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(
            saved.get_config_dict()["property_id"],
            "e00e6034-c154-4754-b5d9-9fff73ad12f6",
        )

    def test_channex_invalid_room_types_json_rejected(self):
        row = self._create_channex_row()
        form = IntegrationConfigAdminForm(
            data=self._channex_form_data(row, room_types_json="{not-json"),
            instance=row,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("room_types_json", form.errors)

    def test_whatsapp_routing_key_sync_on_create(self):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            is_active=True,
        )
        form = IntegrationConfigAdminForm(
            data={
                "tenant": self.tenant.pk,
                "property": "",
                "provider": IntegrationConfig.Provider.WHATSAPP,
                "routing_key": "",
                "is_active": True,
                "phone_number_id": "123456789",
                "display_phone_number": "+385911234567",
                "waba_id": "waba-1",
                "auto_reply": True,
            },
            instance=row,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        config = saved.get_config_dict()
        self.assertEqual(config["phone_number_id"], "123456789")
        self.assertNotIn("access_token", config)
        self.assertEqual(saved.routing_key, "123456789")

    def test_evisitor_password_blank_keeps_existing(self):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.EVISITOR,
            is_active=True,
        )
        row.set_config_dict({"password": "secret-pass", "username": "user1"})
        row.save()

        form = IntegrationConfigAdminForm(
            data={
                "tenant": self.tenant.pk,
                "property": "",
                "provider": IntegrationConfig.Provider.EVISITOR,
                "routing_key": "",
                "is_active": True,
                "password": "",
                "api_key": "",
                "enabled": True,
                "env": "test",
                "base_url": "",
                "username": "user1",
                "facility_code": "",
                "default_arrival_organisation": "I",
                "default_offered_service_type": "noćenje",
                "default_payment_category": "14",
                "default_stay_time_from": "14:00",
                "default_stay_time_until": "10:00",
            },
            instance=row,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.get_config_dict()["password"], "secret-pass")
