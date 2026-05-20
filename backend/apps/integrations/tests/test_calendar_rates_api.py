from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.integrations.models import IntegrationConfig, UnitRateDay
from apps.properties.models import Property, Unit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant

CALENDAR_RATES_URL = "/api/v1/integrations/calendar/rates/"


class CalendarRatesAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="Room 1",
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            property=self.property,
            provider=IntegrationConfig.Provider.SMOOBU,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "api_base": "https://login.smoobu.com",
                "api_key": "test-key",
                "apartments": [
                    {"unit_code": "R1", "smoobu_apartment_id": 3327457, "unit_id": self.unit.id},
                ],
                "push_rates_enabled": True,
            }
        )
        self.integration.save()

        _, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Reception",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.client = APIClient()

    def _auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_get_rates_requires_from_and_to(self):
        response = self.client.get(CALENDAR_RATES_URL, **self._auth_headers())
        self.assertEqual(response.status_code, 400)
        self.assertIn("from", response.json())

    def test_get_rates_returns_stored_days(self):
        UnitRateDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 7, 1),
            rate=Decimal("140.00"),
            min_stay=2,
        )
        response = self.client.get(
            CALENDAR_RATES_URL,
            {"from": "2026-07-01", "to": "2026-07-31", "unit_code": "R1"},
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["from"], "2026-07-01")
        self.assertEqual(len(body["rates"]), 1)
        self.assertEqual(body["rates"][0]["unit_code"], "R1")
        self.assertEqual(body["rates"][0]["rate"], "140.00")

    @patch("apps.integrations.smoobu.rates_service.SmoobuClient")
    def test_patch_rates_persists_and_pushes_to_smoobu(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.post_rates.return_value = {"success": True}
        mock_client_cls.return_value = mock_client

        response = self.client.patch(
            CALENDAR_RATES_URL,
            {
                "updates": [
                    {
                        "unit_code": "R1",
                        "date_from": "2026-08-01",
                        "date_to": "2026-08-03",
                        "rate": "175.00",
                        "min_stay": 2,
                    }
                ]
            },
            format="json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["updated_days"], 3)
        self.assertEqual(body["unsynced_days"], 0)
        self.assertEqual(len(body["push_results"]), 1)
        self.assertTrue(body["push_results"][0]["success"])
        mock_client.post_rates.assert_called_once()

    @patch("apps.integrations.smoobu.rates_service.SmoobuClient")
    def test_patch_with_push_false_skips_smoobu(self, mock_client_cls):
        response = self.client.patch(
            f"{CALENDAR_RATES_URL}?push=false",
            {
                "updates": [
                    {"unit_code": "R1", "date": "2026-08-10", "rate": "99.00"},
                ]
            },
            format="json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["push_results"], [])
        mock_client_cls.assert_not_called()
        row = UnitRateDay.objects.get(unit=self.unit, date=date(2026, 8, 10))
        self.assertIsNone(row.smoobu_synced_at)

    def test_patch_without_smoobu_config_returns_400(self):
        IntegrationConfig.objects.filter(pk=self.integration.pk).update(is_active=False)
        response = self.client.patch(
            CALENDAR_RATES_URL,
            {"updates": [{"unit_code": "R1", "date": "2026-08-01", "rate": "100.00"}]},
            format="json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 400)
