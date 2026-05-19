from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.integrations.channex.ari_payload import build_restriction_value, rate_to_channex_value
from apps.integrations.channex.ari_service import apply_rate_updates, enqueue_outbox_values
from apps.integrations.models import (
    ChannelRatePlan,
    ChannexAriOutbox,
    IntegrationConfig,
    RatePlanDay,
)
from apps.properties.models import Property, Unit
from apps.tenants.models import Tenant


class ChannexAriPayloadTests(TestCase):
    def test_rate_to_channex_value(self):
        self.assertEqual(rate_to_channex_value(Decimal("95.5")), "95.50")

    def test_build_restriction_single_date(self):
        row = build_restriction_value(
            property_id="prop",
            rate_plan_id="rp",
            day="2026-11-22",
            rate=Decimal("333"),
            min_stay_arrival=3,
        )
        self.assertEqual(row["date"], "2026-11-22")
        self.assertEqual(row["rate"], "333.00")


class ChannexAriServiceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="channex-bcom-test",
            name="Test",
            timezone="Europe/Zagreb",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="BCOM-STUDIO",
            name="Studio",
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "environment": "staging",
                "base_url": "https://staging.channex.io/api/v1",
                "property_id": "e00e6034-c154-4754-b5d9-9fff73ad12f6",
                "api_key": "test-key",
                "certification_property_slug": "channex-bcom-test",
                "booking_test_rooms": [
                    {
                        "unit_code": "BCOM-STUDIO",
                        "channex_room_type_id": "18c437d7-13e3-4dbc-9565-48fad4832bf5",
                        "rate_plans": [
                            {
                                "code": "standard",
                                "channex_rate_plan_id": "aa73125c-b9b6-48a7-862f-da68c6e77999",
                                "default_gbp": "95.00",
                            }
                        ],
                    }
                ],
            }
        )
        self.integration.save()
        self.rate_plan = ChannelRatePlan.objects.create(
            tenant=self.tenant,
            property=self.property,
            unit=self.unit,
            code="standard",
            title="Standard",
            channex_room_type_id="18c437d7-13e3-4dbc-9565-48fad4832bf5",
            channex_rate_plan_id="aa73125c-b9b6-48a7-862f-da68c6e77999",
            default_rate=Decimal("95"),
        )

    def test_apply_rate_updates_batches_date_range(self):
        apply_rate_updates(
            self.integration,
            [
                {
                    "unit_code": "BCOM-STUDIO",
                    "rate_plan_code": "standard",
                    "date_from": "2026-11-01",
                    "date_to": "2026-11-10",
                    "rate": "241.00",
                }
            ],
            queue_push=True,
        )
        self.assertEqual(RatePlanDay.objects.filter(rate_plan=self.rate_plan).count(), 10)
        outbox = ChannexAriOutbox.objects.get(
            kind=ChannexAriOutbox.Kind.RESTRICTIONS,
            status=ChannexAriOutbox.Status.PENDING,
        )
        self.assertEqual(len(outbox.values), 1)
        self.assertEqual(outbox.values[0]["date_from"], "2026-11-01")
        self.assertEqual(outbox.values[0]["date_to"], "2026-11-10")

    def test_enqueue_merges_pending_restrictions(self):
        enqueue_outbox_values(
            tenant=self.tenant,
            property=self.property,
            kind=ChannexAriOutbox.Kind.RESTRICTIONS,
            values=[{"rate_plan_id": "a", "date": "2026-11-21"}],
        )
        enqueue_outbox_values(
            tenant=self.tenant,
            property=self.property,
            kind=ChannexAriOutbox.Kind.RESTRICTIONS,
            values=[{"rate_plan_id": "b", "date": "2026-11-25"}],
        )
        outbox = ChannexAriOutbox.objects.filter(kind=ChannexAriOutbox.Kind.RESTRICTIONS)
        self.assertEqual(outbox.count(), 1)
        self.assertEqual(len(outbox.first().values), 2)

    @patch("apps.integrations.channex.ari_service.ChannexClient")
    def test_flush_outbox_posts_restrictions(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.update_restrictions.return_value = {
            "data": [{"id": "task-1", "type": "task"}]
        }
        mock_client.extract_task_ids.return_value = ["task-1"]
        mock_client_cls.return_value = mock_client

        enqueue_outbox_values(
            tenant=self.tenant,
            property=self.property,
            kind=ChannexAriOutbox.Kind.RESTRICTIONS,
            values=[
                build_restriction_value(
                    property_id="e00e6034-c154-4754-b5d9-9fff73ad12f6",
                    rate_plan_id="aa73125c-b9b6-48a7-862f-da68c6e77999",
                    day="2026-11-22",
                    rate=Decimal("333"),
                )
            ],
        )

        from apps.integrations.channex.ari_service import flush_channex_ari_outbox

        results = flush_channex_ari_outbox(self.integration, client=mock_client)
        self.assertEqual(results[0]["task_ids"], ["task-1"])
        mock_client.update_restrictions.assert_called_once()
