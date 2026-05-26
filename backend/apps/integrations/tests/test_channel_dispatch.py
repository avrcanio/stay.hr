from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.integrations.channel_manager.dispatch import create_calendar_block, sync_reservation_outbound
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import ChannelManager, Tenant, TenantReceptionSettings


class ChannelDispatchTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.NONE,
        )
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

    def _create_reservation(self, **overrides):
        defaults = {
            "tenant": self.tenant,
            "property": self.property,
            "check_in": date(2026, 11, 1),
            "check_out": date(2026, 11, 3),
            "status": Reservation.Status.EXPECTED,
            "booker_name": "Guest",
            "source": "reception",
        }
        defaults.update(overrides)
        reservation = Reservation.objects.create(**defaults)
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit,
            room_name="R1",
        )
        return reservation

    def test_none_dispatch_skips(self):
        reservation = self._create_reservation()
        result = sync_reservation_outbound(reservation, action="sync")
        self.assertTrue(result.get("skipped"))
        self.assertEqual(result.get("reason"), "channel_manager_none")

    @patch("apps.integrations.channex.reservation_availability_service.push_availability_range_for_unit")
    @patch("apps.integrations.channex.ari_service.push_channex_ari")
    def test_channex_dispatch_routes_to_availability_service(
        self, mock_push, mock_range
    ):
        TenantReceptionSettings.objects.filter(tenant=self.tenant).update(
            channel_manager=ChannelManager.CHANNEX
        )
        channex = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        channex.set_config_dict(
            {
                "property_id": "prop-id",
                "room_types": [{"unit_code": "R1", "channex_room_type_id": "rt-1"}],
            }
        )
        channex.save()
        mock_range.return_value = {"pushed": True, "unit_code": "R1", "nights": 2}
        mock_push.return_value = []

        reservation = self._create_reservation()
        result = sync_reservation_outbound(reservation, action="sync")
        self.assertTrue(result.get("pushed"))
        mock_range.assert_called_once()
        mock_push.assert_called_once()

    @patch("apps.integrations.channex.ari_service.push_channex_ari")
    @patch("apps.integrations.channex.reservation_availability_service.push_availability_range_for_unit")
    def test_channex_calendar_block_flushes_ari_outbox(self, mock_range, mock_push):
        TenantReceptionSettings.objects.filter(tenant=self.tenant).update(
            channel_manager=ChannelManager.CHANNEX
        )
        channex = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        channex.set_config_dict(
            {
                "property_id": "prop-id",
                "room_types": [{"unit_code": "R1", "channex_room_type_id": "rt-1"}],
            }
        )
        channex.save()
        mock_range.return_value = {"pushed": True, "unit_code": "R1", "nights": 2}
        mock_push.return_value = []

        result = create_calendar_block(
            self.tenant,
            self.unit,
            date(2026, 11, 1),
            date(2026, 11, 3),
        )
        self.assertTrue(result.get("channex_pushed"))
        mock_range.assert_called_once()
        mock_push.assert_called_once()

    def test_none_calendar_block_is_local_only(self):
        result = create_calendar_block(
            self.tenant,
            self.unit,
            date(2026, 11, 1),
            date(2026, 11, 3),
        )
        self.assertIn("block_ref", result)
        self.assertNotIn("channex_pushed", result)
