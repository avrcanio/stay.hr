from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.booking_xls_import import (
    BookingXlsRow,
    import_booking_xls_rows,
    upsert_reservation_from_xls_row,
)
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant


def _sample_row(**overrides) -> BookingXlsRow:
    base = dict(
        external_id="9990001",
        booker_name="Test, Guest",
        guest_names=["Test, Guest"],
        check_in_date=date(2026, 5, 20),
        check_out_date=date(2026, 5, 21),
        booked_at=None,
        booking_status="ok",
        units_count=1,
        persons_count=2,
        adults_count=2,
        children_count=0,
        children_ages="",
        total_amount=Decimal("100.00"),
        currency="EUR",
        commission_percent=None,
        commission_amount=None,
        payment_status="",
        payment_provider="",
        notes="",
        booker_country="HR",
        travel_purpose="",
        booking_device="",
        room_name="Room A",
        nights_count=1,
        canceled_at=None,
        booker_address="",
        booker_phone="",
    )
    base.update(overrides)
    return BookingXlsRow(**base)


class BookingXlsImportSkipExistingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita-import-test")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )

    def test_creates_new_reservation(self):
        row = _sample_row(external_id="1110001")
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
        )
        self.assertTrue(result.created)
        self.assertFalse(result.skipped)
        self.assertEqual(Reservation.objects.filter(external_id="1110001").count(), 1)

    def test_skips_existing_without_touching_guests(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="2220002",
            booking_code="2220002",
            check_in=date(2026, 5, 18),
            check_out=date(2026, 5, 19),
            booker_name="Original Booker",
            status=Reservation.Status.CHECKED_IN,
        )
        guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Original",
            last_name="Guest",
            name="Original Guest",
            is_primary=True,
        )

        row = _sample_row(
            external_id="2220002",
            booker_name="XLS, Intruder",
            guest_names=["XLS, Intruder"],
        )
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
            skip_existing=True,
        )

        self.assertTrue(result.skipped)
        self.assertFalse(result.created)
        reservation.refresh_from_db()
        self.assertEqual(reservation.booker_name, "Original Booker")
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assertEqual(Guest.objects.filter(reservation=reservation).count(), 1)
        guest.refresh_from_db()
        self.assertTrue(guest.is_primary)
        self.assertEqual(guest.name, "Original Guest")

    @patch("apps.reservations.booking_xls_import.parse_booking_xls")
    def test_import_stats_skip_existing(self, mock_parse):
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="3330003",
            booking_code="3330003",
            check_in=date(2026, 5, 20),
            check_out=date(2026, 5, 21),
            booker_name="Exists",
        )
        mock_parse.return_value = [
            _sample_row(external_id="3330003"),
            _sample_row(external_id="4440004"),
        ]
        stats = import_booking_xls_rows(
            tenant=self.tenant,
            property=self.property,
            rows=mock_parse.return_value,
            skip_existing=True,
        )
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["created"], 1)
        self.assertEqual(stats["updated"], 0)
