from datetime import date
from unittest.mock import MagicMock, patch

from django.db import transaction
from django.test import TestCase

from apps.integrations.models import IntegrationConfig, UnitAvailabilityBlock
from apps.integrations.smoobu.reservation_blocking_service import (
    remove_reservation_smoobu_blocks,
    should_sync_smoobu_block,
    sync_reservation_smoobu_blocks,
)
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant


class SmoobuReservationBlockingTests(TestCase):
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
                    {
                        "unit_code": "R1",
                        "smoobu_apartment_id": 3327457,
                        "unit_id": self.unit.id,
                    }
                ],
            }
        )
        self.integration.save()

    def _create_local_reservation(self, **overrides):
        defaults = {
            "tenant": self.tenant,
            "property": self.property,
            "check_in": date(2026, 11, 1),
            "check_out": date(2026, 11, 3),
            "status": Reservation.Status.PENDING,
            "booker_name": "Local Guest",
            "source": "api",
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

    def test_should_sync_local_reservation(self):
        reservation = self._create_local_reservation()
        self.assertTrue(should_sync_smoobu_block(reservation))

    def test_should_not_sync_smoobu_import(self):
        reservation = self._create_local_reservation(import_source="smoobu")
        self.assertFalse(should_sync_smoobu_block(reservation))

    def test_should_not_sync_booking_xls_import(self):
        reservation = self._create_local_reservation(import_source="booking_xls")
        self.assertFalse(should_sync_smoobu_block(reservation))

    def test_should_not_sync_canceled_reservation(self):
        reservation = self._create_local_reservation(status=Reservation.Status.CANCELED)
        self.assertFalse(should_sync_smoobu_block(reservation))

    @patch("apps.integrations.smoobu.blocking_service.SmoobuClient")
    def test_sync_creates_block_with_reservation_link(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.create_reservation.return_value = {"id": 555001}

        reservation = self._create_local_reservation()
        result = sync_reservation_smoobu_blocks(reservation)

        self.assertEqual(len(result["created"]), 1)
        block_row = UnitAvailabilityBlock.objects.get(reservation=reservation)
        self.assertEqual(block_row.smoobu_booking_id, "555001")
        self.assertEqual(block_row.unit_id, self.unit.id)
        mock_client.create_reservation.assert_called_once()

    @patch("apps.integrations.smoobu.blocking_service.SmoobuClient")
    def test_sync_is_idempotent(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.create_reservation.return_value = {"id": 555002}

        reservation = self._create_local_reservation()
        sync_reservation_smoobu_blocks(reservation)
        result = sync_reservation_smoobu_blocks(reservation)

        self.assertEqual(mock_client.create_reservation.call_count, 1)
        self.assertEqual(result["skipped_units"], ["R1"])
        self.assertEqual(
            UnitAvailabilityBlock.objects.filter(reservation=reservation).count(),
            1,
        )

    @patch("apps.integrations.smoobu.blocking_service.SmoobuClient")
    def test_remove_unblocks_reservation_blocks(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.create_reservation.return_value = {"id": 555003}

        reservation = self._create_local_reservation()
        sync_reservation_smoobu_blocks(reservation)

        result = remove_reservation_smoobu_blocks(reservation)

        self.assertEqual(result["removed"], ["555003"])
        mock_client.cancel_reservation.assert_called_once_with("555003")
        self.assertFalse(UnitAvailabilityBlock.objects.filter(reservation=reservation).exists())

class SmoobuReservationBlockingSignalTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita-signal", name="Uzorita Signal")
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

    @patch("apps.integrations.smoobu.tasks.sync_reservation_smoobu_blocks_task")
    def test_signal_schedules_sync_on_create(self, mock_task):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                reservation = Reservation.objects.create(
                    tenant=self.tenant,
                    property=self.property,
                    check_in=date(2026, 12, 1),
                    check_out=date(2026, 12, 3),
                    status=Reservation.Status.PENDING,
                    booker_name="Signal Guest",
                    source="api",
                )
                ReservationUnit.objects.create(
                    tenant=self.tenant,
                    reservation=reservation,
                    unit=self.unit,
                    room_name="R1",
                )

        mock_task.delay.assert_called_once_with(reservation.pk, "sync")

