from django.test import SimpleTestCase

from apps.reservations.models import Reservation


class ReservationStatusTests(SimpleTestCase):
    def test_operational_statuses_exclude_pending(self):
        operational = Reservation.OPERATIONAL_STATUSES
        self.assertIn(Reservation.Status.EXPECTED, operational)
        self.assertIn(Reservation.Status.CHECKED_IN, operational)
        self.assertIn(Reservation.Status.CHECKED_OUT, operational)
        self.assertIn(Reservation.Status.CANCELED, operational)
        self.assertNotIn(Reservation.Status.PENDING, operational)

    def test_pending_remains_for_public_booking_api(self):
        self.assertEqual(Reservation.Status.PENDING, "pending")
