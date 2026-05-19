from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.core.tasks import notify_new_reservation
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class ReservationCreatedSignalTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Demo Property",
            slug="demo",
        )

    @patch("apps.core.tasks.notify_new_reservation.delay")
    def test_create_triggers_notification_task(self, mock_delay):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="SIG-001",
            check_in=date(2026, 5, 21),
            check_out=date(2026, 5, 23),
            status=Reservation.Status.EXPECTED,
            booker_name="Marko Marković",
            amount=Decimal("150.00"),
        )

        mock_delay.assert_called_once_with(reservation.pk)

    @patch("apps.core.tasks.notify_new_reservation.delay")
    def test_update_does_not_trigger(self, mock_delay):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="SIG-002",
            check_in=date(2026, 5, 21),
            check_out=date(2026, 5, 23),
            status=Reservation.Status.EXPECTED,
            booker_name="Marko Marković",
            amount=Decimal("150.00"),
        )
        mock_delay.reset_mock()

        reservation.booker_name = "Updated Name"
        reservation.save()

        mock_delay.assert_not_called()

    @patch("apps.core.tasks.notify_new_reservation.delay")
    def test_canceled_create_skips_notification(self, mock_delay):
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="SIG-003",
            check_in=date(2026, 5, 21),
            check_out=date(2026, 5, 23),
            status=Reservation.Status.CANCELED,
            booker_name="Canceled Guest",
            amount=Decimal("0.00"),
        )

        mock_delay.assert_not_called()
