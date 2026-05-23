from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.integrations.models import IntegrationConfig, UnitAvailabilityBlock
from apps.integrations.smoobu.exceptions import SmoobuRatesError
from apps.integrations.smoobu.tasks import sync_reservation_smoobu_blocks_task
from apps.properties.models import Property, Unit
from apps.reservations.booking_lifecycle import confirm_web_booking, is_web_pending_booking, refuse_web_booking
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import PUBLIC_BOOKING_SCOPES, ApiApplication, Tenant


class BookingLifecycleTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="R1",
        )

    def _pending_web_reservation(self, **overrides):
        defaults = {
            "tenant": self.tenant,
            "property": self.property,
            "booking_code": "ABC12345",
            "check_in": date(2026, 10, 4),
            "check_out": date(2026, 10, 6),
            "status": Reservation.Status.PENDING,
            "booker_name": "Guest Test",
            "booker_email": "guest@example.com",
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

    def test_is_web_pending_booking(self):
        reservation = self._pending_web_reservation()
        self.assertTrue(is_web_pending_booking(reservation))

    def test_is_not_web_pending_when_import_source(self):
        reservation = self._pending_web_reservation(import_source="smoobu")
        self.assertFalse(is_web_pending_booking(reservation))

    @patch("apps.core.tasks.notify_new_reservation.delay")
    @patch("apps.communications.tasks.send_guest_booking_confirmed_email.delay")
    def test_confirm_web_booking(self, mock_email, mock_push):
        reservation = self._pending_web_reservation()
        self.assertTrue(confirm_web_booking(reservation.pk))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPECTED)
        self.assertIsNotNone(reservation.booked_at)
        mock_email.assert_called_once_with(reservation.pk)
        mock_push.assert_called_once_with(reservation.pk)

    @patch("apps.communications.tasks.send_guest_booking_refused_email.delay")
    def test_refuse_web_booking(self, mock_email):
        reservation = self._pending_web_reservation()
        UnitAvailabilityBlock.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reservation=reservation,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            smoobu_booking_id="999",
        )
        self.assertTrue(refuse_web_booking(reservation.pk, reason="overlap"))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.REFUSED)
        mock_email.assert_called_once()
        self.assertFalse(UnitAvailabilityBlock.objects.filter(reservation=reservation).exists())


class SmoobuBookingLifecycleTaskTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita-task")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="R1",
        )
        integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            property=self.property,
            provider=IntegrationConfig.Provider.SMOOBU,
            is_active=True,
        )
        integration.set_config_dict(
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
        integration.save()
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="WEB00001",
            check_in=date(2026, 10, 4),
            check_out=date(2026, 10, 6),
            status=Reservation.Status.PENDING,
            booker_name="Guest",
            booker_email="guest@example.com",
            source="api",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
            room_name="R1",
        )

    @patch("apps.reservations.booking_lifecycle.confirm_web_booking")
    @patch("apps.integrations.smoobu.reservation_blocking_service.sync_reservation_smoobu_blocks")
    def test_task_confirms_on_success(self, mock_sync, mock_confirm):
        mock_sync.return_value = {"created": [{"smoobu_booking_id": "1"}], "skipped_units": []}
        result = sync_reservation_smoobu_blocks_task(self.reservation.pk, "sync")
        self.assertNotIn("refused", result)
        mock_confirm.assert_called_once_with(self.reservation.pk)

    @patch("apps.reservations.booking_lifecycle.refuse_web_booking")
    @patch("apps.integrations.smoobu.reservation_blocking_service.sync_reservation_smoobu_blocks")
    def test_task_refuses_on_conflict(self, mock_sync, mock_refuse):
        mock_sync.side_effect = SmoobuRatesError("Unit is already blocked in the selected range.")
        result = sync_reservation_smoobu_blocks_task(self.reservation.pk, "sync")
        self.assertTrue(result.get("refused"))
        mock_refuse.assert_called_once()


class PublicReservationStatusAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="R1",
        )
        _, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Booking web",
            scopes=PUBLIC_BOOKING_SCOPES,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_token}")

    def test_public_status_lookup(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="STATUS1",
            check_in=date(2026, 10, 4),
            check_out=date(2026, 10, 6),
            status=Reservation.Status.PENDING,
            booker_name="Guest",
            source="api",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit,
            room_name="R1",
        )
        response = self.client.get("/api/v1/public/reservations/STATUS1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["unit_code"], "R1")
