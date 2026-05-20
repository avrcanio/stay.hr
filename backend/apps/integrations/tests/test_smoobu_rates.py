from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.integrations.models import IntegrationConfig, UnitRateDay
from apps.integrations.smoobu.rates_service import (
    apply_rate_updates,
    build_rate_operation,
    push_smoobu_rates,
)
from apps.properties.models import Property, Unit
from apps.tenants.models import Tenant


class SmoobuRatesServiceTests(TestCase):
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

    def test_build_rate_operation_single_date(self):
        op = build_rate_operation(
            day=date(2026, 6, 1),
            day_to=date(2026, 6, 1),
            rate=Decimal("140.00"),
            min_stay=2,
        )
        self.assertEqual(op["dates"], ["2026-06-01"])
        self.assertEqual(op["daily_price"], 140.0)
        self.assertEqual(op["min_length_of_stay"], 2)

    def test_build_rate_operation_date_range(self):
        op = build_rate_operation(
            day=date(2026, 6, 1),
            day_to=date(2026, 6, 10),
            rate=Decimal("200.00"),
            min_stay=None,
        )
        self.assertEqual(op["dates"], ["2026-06-01:2026-06-10"])
        self.assertNotIn("min_length_of_stay", op)

    @patch("apps.integrations.smoobu.rates_service.SmoobuClient")
    def test_apply_rate_updates_persists_and_pushes(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.post_rates.return_value = {"success": True}
        mock_client_cls.return_value = mock_client

        rows, push_results = apply_rate_updates(
            self.integration,
            [
                {
                    "unit_code": "R1",
                    "date_from": "2026-06-01",
                    "date_to": "2026-06-03",
                    "rate": "150.00",
                    "min_stay_arrival": 2,
                }
            ],
            push=True,
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(len(push_results), 1)
        self.assertEqual(UnitRateDay.objects.filter(unit=self.unit).count(), 3)
        mock_client.post_rates.assert_called_once()
        call_kwargs = mock_client.post_rates.call_args.kwargs
        self.assertEqual(call_kwargs["apartment_ids"], [3327457])
        self.assertEqual(len(call_kwargs["operations"]), 1)
        self.assertEqual(call_kwargs["operations"][0]["dates"], ["2026-06-01:2026-06-03"])
        self.assertEqual(call_kwargs["operations"][0]["daily_price"], 150.0)

        for row in UnitRateDay.objects.filter(unit=self.unit):
            self.assertIsNotNone(row.smoobu_synced_at)

    @patch("apps.integrations.smoobu.rates_service.SmoobuClient")
    def test_apply_rate_updates_without_push_leaves_unsynced(self, mock_client_cls):
        rows, push_results = apply_rate_updates(
            self.integration,
            [{"unit_code": "R1", "date": "2026-06-01", "rate": "120.00"}],
            push=False,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(push_results, [])
        mock_client_cls.assert_not_called()
        row = UnitRateDay.objects.get(unit=self.unit, date=date(2026, 6, 1))
        self.assertIsNone(row.smoobu_synced_at)

    @patch("apps.integrations.smoobu.rates_service.SmoobuClient")
    def test_push_smoobu_rates_flushes_unsynced(self, mock_client_cls):
        UnitRateDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 6, 5),
            rate=Decimal("99.00"),
            min_stay=1,
        )
        mock_client = MagicMock()
        mock_client.post_rates.return_value = {"success": True}
        mock_client_cls.return_value = mock_client

        results = push_smoobu_rates(self.integration)

        self.assertEqual(len(results), 1)
        row = UnitRateDay.objects.get(unit=self.unit, date=date(2026, 6, 5))
        self.assertIsNotNone(row.smoobu_synced_at)
