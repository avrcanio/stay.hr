from datetime import date

from django.test import SimpleTestCase

from apps.legacy_import.mapping import map_legacy_status, reservation_fingerprint
from apps.reservations.models import Reservation


class MapLegacyStatusTests(SimpleTestCase):
    def test_uzorita_operational_unchanged(self):
        self.assertEqual(map_legacy_status("checked_in"), Reservation.Status.CHECKED_IN)

    def test_booking_statuses_map_to_operational(self):
        self.assertEqual(map_legacy_status("pending"), Reservation.Status.EXPECTED)
        self.assertEqual(map_legacy_status("confirmed"), Reservation.Status.EXPECTED)
        self.assertEqual(map_legacy_status("cancelled"), Reservation.Status.CANCELED)


class ReservationFingerprintTests(SimpleTestCase):
    def test_stable_hash(self):
        fp1 = reservation_fingerprint(date(2025, 6, 1), "expected", 2)
        fp2 = reservation_fingerprint(date(2025, 6, 1), "expected", 2)
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)
