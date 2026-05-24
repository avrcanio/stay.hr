from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.integrations.channex.reservation_availability_service import (
    compute_unit_availability,
    should_sync_channex_availability,
    sync_reservation_channex_availability,
)
from apps.integrations.models import IntegrationConfig, UnitAvailabilityBlock
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import ChannelManager, Tenant, TenantReceptionSettings


class ChannexReservationAvailabilityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="demo", name="Demo")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="channex-demo",
            name="Demo",
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
                "property_id": "prop-id",
                "room_types": [
                    {
                        "unit_code": "BCOM-STUDIO",
                        "channex_room_type_id": "rt-1",
                    }
                ],
            }
        )
        self.integration.save()

    def _create_reservation(self, **overrides):
        defaults = {
            "tenant": self.tenant,
            "property": self.property,
            "check_in": date(2026, 11, 1),
            "check_out": date(2026, 11, 3),
            "status": Reservation.Status.EXPECTED,
            "booker_name": "Guest",
            "import_source": "manual",
        }
        defaults.update(overrides)
        reservation = Reservation.objects.create(**defaults)
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit,
            room_name="Studio",
        )
        return reservation

    def test_should_not_sync_channex_import(self):
        reservation = self._create_reservation(import_source="channex")
        self.assertFalse(should_sync_channex_availability(reservation))

    def test_compute_unit_availability_open(self):
        self.assertEqual(
            compute_unit_availability(self.tenant, self.unit, date(2026, 11, 1)),
            1,
        )

    def test_compute_unit_availability_blocked_by_reservation(self):
        reservation = self._create_reservation()
        self.assertEqual(
            compute_unit_availability(self.tenant, self.unit, date(2026, 11, 1)),
            0,
        )
        reservation.status = Reservation.Status.CANCELED
        reservation.save()
        self.assertEqual(
            compute_unit_availability(self.tenant, self.unit, date(2026, 11, 1)),
            1,
        )

    def test_compute_unit_availability_blocked_by_manual_block(self):
        UnitAvailabilityBlock.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            check_in=date(2026, 11, 1),
            check_out=date(2026, 11, 2),
            smoobu_booking_id="local:test",
        )
        self.assertEqual(
            compute_unit_availability(self.tenant, self.unit, date(2026, 11, 1)),
            0,
        )

    @patch("apps.integrations.channex.reservation_availability_service.apply_availability_updates")
    @patch("apps.integrations.channex.ari_service.push_channex_ari")
    def test_sync_pushes_zero_for_blocked_nights(self, mock_push, mock_apply):
        mock_apply.return_value = []
        mock_push.return_value = []
        reservation = self._create_reservation()
        result = sync_reservation_channex_availability(reservation)
        self.assertTrue(result.get("pushed"))
        mock_apply.assert_called_once()
        updates = mock_apply.call_args.args[1]
        self.assertEqual(len(updates), 2)
        self.assertTrue(all(item["availability"] == 0 for item in updates))
