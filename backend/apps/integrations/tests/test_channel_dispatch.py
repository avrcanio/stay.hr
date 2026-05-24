from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.integrations.channel_manager.dispatch import sync_reservation_outbound
from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.reservation_blocking_service import should_sync_smoobu_block
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import ChannelManager, Tenant, TenantReceptionSettings


class ChannelDispatchTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.SMOOBU,
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
                    {
                        "unit_code": "R1",
                        "smoobu_apartment_id": 3327457,
                        "unit_id": self.unit.id,
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

    @patch("apps.integrations.smoobu.reservation_blocking_service.block_apartment_dates")
    def test_smoobu_dispatch_routes_to_block_service(self, mock_block):
        mock_block.return_value = {
            "id": 1,
            "smoobu_booking_id": "123",
            "unit_code": "R1",
            "unit_id": self.unit.id,
            "check_in": "2026-11-01",
            "check_out": "2026-11-03",
        }
        reservation = self._create_reservation()
        self.assertTrue(should_sync_smoobu_block(reservation))
        result = sync_reservation_outbound(reservation, action="sync")
        self.assertFalse(result.get("skipped"))
        mock_block.assert_called_once()

    def test_none_dispatch_skips(self):
        TenantReceptionSettings.objects.filter(tenant=self.tenant).update(
            channel_manager=ChannelManager.NONE
        )
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
        IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        channex = IntegrationConfig.objects.get(
            tenant=self.tenant, provider=IntegrationConfig.Provider.CHANNEX
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
