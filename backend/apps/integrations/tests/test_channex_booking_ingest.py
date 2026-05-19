from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.integrations.channex.booking_service import (
    channex_external_id,
    process_channex_booking_revision,
)
from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.models import ChannexBookingRevision, IntegrationConfig
from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import Tenant


class ChannexBookingIngestTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="channex-bcom-test",
            name="Booking test",
            timezone="Europe/Zagreb",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="BCOM-STUDIO",
            name="Studio",
            capacity_adults=2,
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
                        "unit_id": self.unit.id,
                        "channex_room_type_id": "18c437d7-13e3-4dbc-9565-48fad4832bf5",
                        "channex_title": "Studio",
                    }
                ],
            }
        )
        self.integration.save()

        self.revision_id = "09a123e3-9011-4077-b0fa-357b01e86bd5"
        self.booking_id = "164f2183-454c-40ea-905d-d79859136236"
        self.revision_payload = {
            "id": self.revision_id,
            "attributes": {
                "booking_id": self.booking_id,
                "status": "new",
                "arrival_date": "2026-05-19",
                "departure_date": "2026-05-23",
                "amount": "316.00",
                "currency": "GBP",
                "ota_name": "Offline",
                "inserted_at": "2026-05-19T05:50:12.114152Z",
                "occupancy": {"adults": 1, "children": 0, "infants": 0},
                "customer": {
                    "name": "Ante",
                    "surname": "Vrcan",
                    "mail": "guest@example.com",
                    "phone": "0976713511",
                    "address": "Test street 1",
                    "city": "Šibenik",
                },
                "rooms": [
                    {
                        "amount": "316.00",
                        "room_type_id": "18c437d7-13e3-4dbc-9565-48fad4832bf5",
                        "rate_plan_id": "6734ae1e-70bb-4217-b668-2aa8720bca13",
                    }
                ],
            },
        }

    def test_channex_external_id_prefix(self):
        self.assertEqual(
            channex_external_id("abc"),
            "channex:abc",
        )

    def test_booking_test_room_lookup(self):
        config = ChannexRuntimeConfig.from_integration_dict(self.integration.get_config_dict())
        link = config.booking_test_room_for_channex_room_type_id(
            "18c437d7-13e3-4dbc-9565-48fad4832bf5"
        )
        self.assertIsNotNone(link)
        self.assertEqual(link.unit_code, "BCOM-STUDIO")

    @patch("apps.integrations.channex.booking_service.ChannexClient")
    def test_ingest_creates_reservation_and_acknowledges(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get_booking_revision.return_value = self.revision_payload
        mock_client_cls.return_value = mock_client

        reservation = process_channex_booking_revision(
            self.integration,
            self.revision_id,
        )

        self.assertEqual(reservation.external_id, channex_external_id(self.booking_id))
        self.assertEqual(reservation.check_in, date(2026, 5, 19))
        self.assertEqual(reservation.check_out, date(2026, 5, 23))
        self.assertEqual(reservation.status, Reservation.Status.EXPECTED)
        self.assertEqual(reservation.booker_name, "Ante Vrcan")
        self.assertEqual(reservation.amount, Decimal("316.00"))
        self.assertEqual(reservation.currency, "GBP")
        self.assertEqual(reservation.source, "Offline")

        units = list(ReservationUnit.objects.filter(reservation=reservation))
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].unit_id, self.unit.id)
        self.assertEqual(units[0].room_name, "Studio")

        guest = Guest.objects.get(reservation=reservation, is_primary=True)
        self.assertEqual(guest.first_name, "Ante")
        self.assertEqual(guest.last_name, "Vrcan")

        mock_client.acknowledge_booking_revision.assert_called_once_with(self.revision_id)
        self.assertTrue(
            ChannexBookingRevision.objects.filter(revision_id=self.revision_id).exists()
        )

    @patch("apps.integrations.channex.booking_service.ChannexClient")
    def test_ingest_is_idempotent_per_revision(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get_booking_revision.return_value = self.revision_payload
        mock_client_cls.return_value = mock_client

        first = process_channex_booking_revision(self.integration, self.revision_id)
        second = process_channex_booking_revision(self.integration, self.revision_id)

        self.assertEqual(first.id, second.id)
        mock_client.get_booking_revision.assert_called_once()
        mock_client.acknowledge_booking_revision.assert_called_once()

    @patch("apps.integrations.channex.booking_service.ChannexClient")
    def test_cancelled_revision_updates_status(self, mock_client_cls):
        cancelled = dict(self.revision_payload)
        cancelled["attributes"] = dict(self.revision_payload["attributes"])
        cancelled["attributes"]["status"] = "cancelled"

        mock_client = MagicMock()
        mock_client.get_booking_revision.return_value = cancelled
        mock_client_cls.return_value = mock_client

        reservation = process_channex_booking_revision(
            self.integration,
            self.revision_id,
        )
        self.assertEqual(reservation.status, Reservation.Status.CANCELED)
        self.assertIsNotNone(reservation.canceled_at)
