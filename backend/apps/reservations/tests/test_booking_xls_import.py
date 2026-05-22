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
from apps.reservations.guest_slots import PLACEHOLDER_NAME
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

    def test_creates_placeholder_guests_for_missing_adults(self):
        row = _sample_row(external_id="6660006", adults_count=2, guest_names=["Test, Guest"])
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
        )
        self.assertTrue(result.created)
        reservation = Reservation.objects.get(external_id="6660006")
        guests = list(reservation.guests.order_by("-is_primary", "id"))
        self.assertEqual(len(guests), 2)
        self.assertTrue(guests[0].is_primary)
        self.assertEqual(guests[0].name, "Guest Test")
        self.assertFalse(guests[1].is_primary)
        self.assertEqual(guests[1].name, PLACEHOLDER_NAME)

    def test_fill_empty_adds_placeholder_guests_for_missing_adults(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="7770007",
            booking_code="7770007",
            check_in=date(2026, 5, 20),
            check_out=date(2026, 5, 21),
            booker_name="Original Booker",
            adults_count=2,
            status=Reservation.Status.EXPECTED,
        )
        guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Original",
            last_name="Booker",
            name="Original Booker",
            is_primary=True,
        )

        row = _sample_row(
            external_id="7770007",
            adults_count=2,
            guest_names=["Original Booker"],
        )
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
            existing_mode="fill_empty",
        )

        self.assertTrue(result.merged)
        self.assertEqual(Guest.objects.filter(reservation=reservation).count(), 2)
        guest.refresh_from_db()
        self.assertEqual(guest.name, "Original Booker")
        self.assertTrue(
            Guest.objects.filter(
                reservation=reservation,
                is_primary=False,
                name=PLACEHOLDER_NAME,
            ).exists()
        )

    def test_does_not_add_placeholders_for_children_only(self):
        row = _sample_row(
            external_id="8880008",
            adults_count=2,
            children_count=1,
            persons_count=3,
            guest_names=["Test, Guest"],
        )
        upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
        )
        reservation = Reservation.objects.get(external_id="8880008")
        self.assertEqual(Guest.objects.filter(reservation=reservation).count(), 2)

    def test_single_adult_has_no_placeholder(self):
        row = _sample_row(
            external_id="8890009",
            adults_count=1,
            persons_count=1,
            guest_names=["Test, Guest"],
        )
        upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
        )
        reservation = Reservation.objects.get(external_id="8890009")
        self.assertEqual(Guest.objects.filter(reservation=reservation).count(), 1)

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

    def test_fill_empty_merges_blank_fields_only(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5550005",
            booking_code="5550005",
            check_in=date(2026, 5, 20),
            check_out=date(2026, 5, 21),
            booker_name="Original Booker",
            booker_phone="",
            status=Reservation.Status.CHECKED_IN,
        )
        guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Original",
            last_name="Booker",
            name="Original Booker",
            is_primary=True,
        )

        row = _sample_row(
            external_id="5550005",
            booker_name="XLS, Name",
            guest_names=["XLS, Name"],
            booker_phone="+385991234567",
            adults_count=1,
        )
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
            existing_mode="fill_empty",
        )

        self.assertTrue(result.merged)
        self.assertFalse(result.created)
        reservation.refresh_from_db()
        self.assertEqual(reservation.booker_name, "Original Booker")
        self.assertEqual(reservation.booker_phone, "+385991234567")
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assertEqual(Guest.objects.filter(reservation=reservation).count(), 1)
        guest.refresh_from_db()
        self.assertEqual(guest.name, "Original Booker")

    def test_fill_empty_merges_guest_when_xls_name_parsing_differs(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="6262102168",
            booking_code="6262102168",
            check_in=date(2026, 9, 18),
            check_out=date(2026, 9, 19),
            booker_name="Maria Hernando Sanz",
            booker_country="ES",
            status=Reservation.Status.EXPECTED,
        )
        guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Maria",
            last_name="Hernando Sanz",
            name="Maria Hernando Sanz",
            is_primary=True,
        )

        row = _sample_row(
            external_id="6262102168",
            booker_name="Hernando Sanz, Maria",
            guest_names=["Maria Hernando Sanz"],
            booker_country="ES",
        )
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
            existing_mode="fill_empty",
        )

        self.assertTrue(result.merged)
        guest.refresh_from_db()
        self.assertEqual(guest.nationality, "ES")
        self.assertEqual(guest.document_country_iso2, "ES")
