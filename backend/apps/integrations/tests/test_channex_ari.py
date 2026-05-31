from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.integrations.channex.ari_payload import (
    build_restriction_value,
    rate_to_channex_value,
    restriction_delta_from_update,
)
from apps.integrations.channex.ari_service import (
    apply_rate_updates,
    build_full_sync,
    compress_availability_days_to_values,
    enqueue_outbox_values,
)
from apps.integrations.channex.demo_property import CHANNEX_DEMO_PROPERTY_SLUG
from apps.integrations.models import (
    ChannelRatePlan,
    ChannexAriOutbox,
    IntegrationConfig,
    RatePlanDay,
    SalesChannel,
    UnitAvailabilityDay,
)
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant

FULL_SYNC_RESTRICTION_KEYS = frozenset(
    {
        "min_stay_through",
        "max_stay",
        "stop_sell",
        "closed_to_arrival",
        "closed_to_departure",
    }
)


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

    def test_restriction_delta_from_update_rate_only(self):
        class Sample:
            rate = Decimal("333.00")
            min_stay_arrival = 1
            min_stay_through = 1
            max_stay = 30
            stop_sell = False
            closed_to_arrival = False
            closed_to_departure = False

        row = restriction_delta_from_update(
            {"rate": "333.00"},
            Sample(),
            property_id="prop",
            rate_plan_id="rp",
            day="2026-11-22",
        )
        self.assertEqual(
            set(row.keys()),
            {"property_id", "rate_plan_id", "date", "rate"},
        )


class ChannexAriServiceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="demo", name="Demo")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug=CHANNEX_DEMO_PROPERTY_SLUG,
            name="Test Property - Stay.hr",
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
                "certification_property_slug": CHANNEX_DEMO_PROPERTY_SLUG,
                "use_generated_ari": True,
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
            sales_channel=SalesChannel.BOOKING_COM,
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
        value = outbox.values[0]
        self.assertEqual(value["date_from"], "2026-11-01")
        self.assertEqual(value["date_to"], "2026-11-10")
        self.assertEqual(set(value.keys()), {"property_id", "rate_plan_id", "date_from", "date_to", "rate"})

    def test_apply_rate_updates_direct_no_outbox(self):
        direct_plan = ChannelRatePlan.objects.create(
            tenant=self.tenant,
            property=self.property,
            unit=self.unit,
            sales_channel=SalesChannel.DIRECT,
            code="standard",
            title="Standard direct",
            default_rate=Decimal("90"),
        )
        apply_rate_updates(
            self.integration,
            [
                {
                    "unit_code": "BCOM-STUDIO",
                    "rate_plan_code": "standard",
                    "sales_channel": SalesChannel.DIRECT,
                    "date_from": "2026-11-01",
                    "date_to": "2026-11-03",
                    "rate": "88.00",
                }
            ],
            queue_push=True,
        )
        self.assertEqual(RatePlanDay.objects.filter(rate_plan=direct_plan).count(), 3)
        self.assertFalse(ChannexAriOutbox.objects.filter(kind=ChannexAriOutbox.Kind.RESTRICTIONS).exists())

    def test_apply_rate_updates_rate_only_delta(self):
        RatePlanDay.objects.create(
            tenant=self.tenant,
            rate_plan=self.rate_plan,
            date=date(2026, 11, 22),
            rate=Decimal("100.00"),
            min_stay_arrival=1,
            min_stay_through=1,
            max_stay=30,
            stop_sell=False,
            closed_to_arrival=False,
            closed_to_departure=False,
        )
        apply_rate_updates(
            self.integration,
            [
                {
                    "unit_code": "BCOM-STUDIO",
                    "rate_plan_code": "standard",
                    "date": "2026-11-22",
                    "rate": "333.00",
                }
            ],
            queue_push=True,
        )
        outbox = ChannexAriOutbox.objects.get(
            kind=ChannexAriOutbox.Kind.RESTRICTIONS,
            status=ChannexAriOutbox.Status.PENDING,
        )
        value = outbox.values[0]
        self.assertEqual(
            set(value.keys()),
            {"property_id", "rate_plan_id", "date", "rate"},
        )
        self.assertEqual(value["rate"], "338.00")
        self.assertNotIn("min_stay_arrival", value)
        self.assertNotIn("stop_sell", value)

    def test_build_full_sync_restriction_payload_complete(self):
        _, restriction_values = build_full_sync(
            self.integration,
            days=31,
            start=date(2026, 6, 1),
        )
        self.assertGreater(len(restriction_values), 0)
        for batch in restriction_values:
            self.assertTrue(FULL_SYNC_RESTRICTION_KEYS.issubset(batch.keys()))

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


class CompressAvailabilityDaysTests(TestCase):
    def test_groups_consecutive_days_with_same_availability(self):
        values = compress_availability_days_to_values(
            property_id="prop",
            room_type_id="room",
            days=[
                (date(2026, 5, 26), 1),
                (date(2026, 5, 27), 0),
                (date(2026, 5, 28), 0),
                (date(2026, 5, 29), 1),
            ],
        )
        self.assertEqual(len(values), 3)
        self.assertEqual(values[0]["availability"], 1)
        self.assertEqual(values[0]["date_from"], "2026-05-26")
        self.assertEqual(values[1]["availability"], 0)
        self.assertEqual(values[1]["date_from"], "2026-05-27")
        self.assertEqual(values[1]["date_to"], "2026-05-28")
        self.assertEqual(values[2]["availability"], 1)
        self.assertEqual(values[2]["date_from"], "2026-05-29")


class ChannexInventoryFullSyncTests(TestCase):
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
            name="R1",
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "environment": "production",
                "base_url": "https://app.channex.io/api/v1",
                "property_id": "bca8473d-7c36-4986-bcdb-b5760b633283",
                "sync_property_slug": "uzorita",
                "use_generated_ari": False,
                "room_types": [
                    {
                        "unit_code": "R1",
                        "unit_id": self.unit.id,
                        "channex_room_type_id": "room-r1",
                        "channex_title": "Luxury Room Uzorita - R1",
                    }
                ],
            }
        )
        self.integration.save()
        self.rate_plan = ChannelRatePlan.objects.create(
            tenant=self.tenant,
            property=self.property,
            unit=self.unit,
            sales_channel=SalesChannel.BOOKING_COM,
            code="standard",
            title="Standard",
            channex_room_type_id="room-r1",
            channex_rate_plan_id="rate-r1",
            default_rate=Decimal("95"),
        )

    def test_full_sync_pushes_zero_availability_for_blocked_nights(self):
        incumbent = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="6931685558",
            booking_code="6931685558",
            booker_name="Sladjana SKORIC",
            check_in=date(2026, 5, 27),
            check_out=date(2026, 5, 29),
            status=Reservation.Status.EXPECTED,
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=incumbent,
            unit=self.unit,
            room_name="Luxury Room Uzorita - R1",
        )

        availability_values, _ = build_full_sync(
            self.integration,
            days=5,
            start=date(2026, 5, 26),
        )

        blocked = [row for row in availability_values if row["availability"] == 0]
        self.assertTrue(blocked)
        self.assertTrue(
            any(
                row["date_from"] <= "2026-05-27" <= row["date_to"]
                for row in blocked
            )
        )
        self.assertFalse(
            any(
                row["availability"] == 1
                and row["date_from"] == "2026-05-26"
                and row["date_to"] == "2026-05-30"
                for row in availability_values
            )
        )
        self.assertEqual(
            UnitAvailabilityDay.objects.get(unit=self.unit, date=date(2026, 5, 27)).availability,
            0,
        )
