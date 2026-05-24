from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.properties.models import Property
from apps.reservations.booking_pdf_import import parse_booking_pdf_text
from apps.reservations.booking_xls_import import (
    BookingXlsRow,
    import_booking_xls_rows,
    upsert_reservation_from_xls_row,
)
from apps.reservations.guest_slots import PLACEHOLDER_FIRST, PLACEHOLDER_LAST, PLACEHOLDER_NAME
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant

IMPORTS = Path(__file__).resolve().parents[4] / ".imports"

MULTI_ROOM_PDF_TEXT = """
Luxury Room Uzorita B&B
Check-in
Sun, May 25, 2026
Check-out
Mon, May 26, 2026
Total guests:
4 adults
Total units
2
Total price
€ 201.65
Guest name:
Kris Meeus
 be
kmeeus.604082@guest.booking.com
Booking number:
5898434847
Deluxe King Room (Luxury Room Uzorita - R2)
€ 109.00
Guest Name
Kurt Meeus
Booked occupancy
2 adults
Total room price
€ 109.00
Deluxe King Room (Luxury Room Uzorita - R1)
€ 92.65
Guest Name
Kris Meeus
Booked occupancy
2 adults
Total room price
€ 92.65
"""


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

    def test_skips_stale_xls_when_smoobu_newer(self):
        smoobu_at = timezone.now() + timedelta(hours=1)
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="2220002",
            booking_code="2220002",
            check_in=date(2026, 5, 18),
            check_out=date(2026, 5, 19),
            booker_name="Original Booker",
            status=Reservation.Status.CHECKED_IN,
            smoobu_modified_at=smoobu_at,
            imported_at=smoobu_at,
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
        )

        self.assertTrue(result.skipped)
        self.assertEqual(result.skip_reason, "stale_xls")
        self.assertFalse(result.created)
        reservation.refresh_from_db()
        self.assertEqual(reservation.booker_name, "Original Booker")
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assertEqual(Guest.objects.filter(reservation=reservation).count(), 1)
        guest.refresh_from_db()
        self.assertTrue(guest.is_primary)
        self.assertEqual(guest.name, "Original Guest")

    def test_overwrites_existing_when_xls_newer_than_smoobu(self):
        smoobu_at = timezone.now() - timedelta(days=1)
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="2220003",
            booking_code="2220003",
            check_in=date(2026, 5, 18),
            check_out=date(2026, 5, 19),
            booker_name="Smoobu Guest",
            status=Reservation.Status.EXPECTED,
            smoobu_modified_at=smoobu_at,
            imported_at=smoobu_at,
            import_source="smoobu",
        )

        row = _sample_row(
            external_id="2220003",
            booker_name="XLS, Winner",
            guest_names=["XLS, Winner"],
        )
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
        )

        self.assertFalse(result.skipped)
        self.assertTrue(result.updated)
        reservation.refresh_from_db()
        self.assertEqual(reservation.booker_name, "XLS, Winner")
        self.assertEqual(reservation.import_source, "booking_xls")
        self.assertIsNotNone(reservation.xls_imported_at)

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
    def test_import_stats_sync_existing(self, mock_parse):
        smoobu_at = timezone.now() + timedelta(hours=1)
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="3330003",
            booking_code="3330003",
            check_in=date(2026, 5, 20),
            check_out=date(2026, 5, 21),
            booker_name="Exists",
            smoobu_modified_at=smoobu_at,
            imported_at=smoobu_at,
        )
        mock_parse.return_value = [
            _sample_row(external_id="3330003"),
            _sample_row(external_id="4440004"),
        ]
        stats = import_booking_xls_rows(
            tenant=self.tenant,
            property=self.property,
            rows=mock_parse.return_value,
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

    def test_skips_xls_when_pdf_locked(self):
        pdf_at = timezone.now()
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="9998887",
            booking_code="9998887",
            check_in=date(2026, 7, 1),
            check_out=date(2026, 7, 6),
            booker_name="PDF Guest",
            status=Reservation.Status.EXPECTED,
            import_source="booking_pdf",
            pdf_imported_at=pdf_at,
            xls_imported_at=pdf_at,
        )
        row = _sample_row(
            external_id="9998887",
            booker_name="XLS, Intruder",
        )
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
            existing_mode="overwrite",
        )
        self.assertTrue(result.skipped)
        self.assertEqual(result.skip_reason, "pdf_locked")
        reservation.refresh_from_db()
        self.assertEqual(reservation.booker_name, "PDF Guest")

    def test_authoritative_pdf_overwrite_sets_pdf_marker(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="9998888",
            booking_code="9998888",
            check_in=date(2026, 7, 1),
            check_out=date(2026, 7, 6),
            booker_name="Smoobu Guest",
            status=Reservation.Status.EXPECTED,
            import_source="smoobu",
        )
        row = _sample_row(
            external_id="9998888",
            booker_name="PDF, Winner",
            guest_names=["PDF, Winner"],
        )
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
            existing_mode="overwrite",
            authoritative_pdf=True,
        )
        self.assertFalse(result.skipped)
        self.assertTrue(result.updated)
        reservation.refresh_from_db()
        self.assertEqual(reservation.booker_name, "PDF, Winner")
        self.assertEqual(reservation.import_source, "booking_pdf")
        self.assertIsNotNone(reservation.pdf_imported_at)
        self.assertIsNotNone(reservation.xls_imported_at)

    def test_authoritative_pdf_overwrite_preserves_existing_contact(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="9998889",
            booking_code="9998889",
            check_in=date(2026, 7, 1),
            check_out=date(2026, 7, 6),
            booker_name="Smoobu Guest",
            booker_phone="+31 31629557900",
            booker_email="keep@example.com",
            status=Reservation.Status.EXPECTED,
            import_source="smoobu",
        )
        guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Smoobu",
            last_name="Guest",
            email="keep@example.com",
            is_primary=True,
        )
        row = _sample_row(
            external_id="9998889",
            booker_name="PDF, Winner",
            guest_names=["PDF, Winner"],
            booker_phone="",
            booker_email="new@example.com",
        )
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
            existing_mode="overwrite",
            authoritative_pdf=True,
        )
        self.assertFalse(result.skipped)
        self.assertTrue(result.updated)
        reservation.refresh_from_db()
        guest.refresh_from_db()
        self.assertEqual(reservation.booker_name, "PDF, Winner")
        self.assertEqual(reservation.booker_phone, "+31 31629557900")
        self.assertEqual(reservation.booker_email, "keep@example.com")
        self.assertEqual(guest.email, "keep@example.com")

    def test_authoritative_pdf_dedupes_smoobu_name_split(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="6950508284",
            booking_code="6950508284",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            booker_name="Francisco Caimaris Villalonga",
            adults_count=2,
            status=Reservation.Status.EXPECTED,
            import_source="smoobu",
        )
        smoobu_guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Francisco",
            last_name="Caimaris Villalonga",
            name="Francisco Caimaris Villalonga",
            nationality="ES",
            is_primary=True,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name=PLACEHOLDER_FIRST,
            last_name=PLACEHOLDER_LAST,
            name=PLACEHOLDER_NAME,
            is_primary=False,
        )

        pdf_path = IMPORTS / "6950508284.pdf"
        if not pdf_path.exists():
            self.skipTest("Sample PDF not available")
        row = parse_booking_pdf(pdf_path.read_bytes())

        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
            existing_mode="overwrite",
            authoritative_pdf=True,
        )

        self.assertFalse(result.skipped)
        self.assertTrue(result.updated)
        reservation.refresh_from_db()
        self.assertEqual(reservation.booker_country, "ES")
        self.assertEqual(reservation.import_source, "booking_pdf")

        guests = list(reservation.guests.order_by("-is_primary", "id"))
        self.assertEqual(len(guests), 2)
        self.assertTrue(guests[0].is_primary)
        self.assertEqual(guests[0].first_name, "Francisco Caimaris")
        self.assertEqual(guests[0].last_name, "Villalonga")
        self.assertEqual(guests[0].name, "Francisco Caimaris Villalonga")
        self.assertEqual(guests[0].nationality, "ES")
        self.assertEqual(guests[0].id, smoobu_guest.id)
        self.assertFalse(guests[1].is_primary)
        self.assertEqual(guests[1].name, PLACEHOLDER_NAME)
        self.assertEqual(
            Guest.objects.filter(
                reservation=reservation,
                name="Francisco Caimaris Villalonga",
            ).count(),
            1,
        )

    def test_authoritative_pdf_syncs_multi_room_guests(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5898434847",
            booking_code="5898434847",
            check_in=date(2026, 5, 25),
            check_out=date(2026, 5, 26),
            booker_name="Kurt Meeus",
            adults_count=4,
            units_count=1,
            status=Reservation.Status.EXPECTED,
            import_source="smoobu",
        )
        kurt_guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Kurt",
            last_name="Meeus",
            name="Kurt Meeus",
            nationality="BE",
            is_primary=True,
        )

        row = parse_booking_pdf_text(MULTI_ROOM_PDF_TEXT)
        result = upsert_reservation_from_xls_row(
            tenant=self.tenant,
            property=self.property,
            row=row,
            existing_mode="overwrite",
            authoritative_pdf=True,
        )

        self.assertFalse(result.skipped)
        self.assertTrue(result.updated)
        reservation.refresh_from_db()
        self.assertEqual(reservation.booker_name, "Kris Meeus")
        self.assertEqual(reservation.booker_country, "BE")
        self.assertEqual(reservation.units_count, 2)
        self.assertEqual(reservation.adults_count, 4)
        self.assertEqual(reservation.import_source, "booking_pdf")

        named_guests = [
            guest
            for guest in reservation.guests.order_by("-is_primary", "id")
            if guest.name != PLACEHOLDER_NAME
        ]
        self.assertEqual(len(named_guests), 2)
        self.assertEqual(named_guests[0].name, "Kris Meeus")
        self.assertTrue(named_guests[0].is_primary)
        self.assertEqual(named_guests[1].name, "Kurt Meeus")
        self.assertFalse(named_guests[1].is_primary)
        self.assertEqual(named_guests[1].id, kurt_guest.id)

        units = list(reservation.units.order_by("sort_order"))
        self.assertEqual(len(units), 2)
        self.assertIn("R2", units[0].room_name)
        self.assertIn("R1", units[1].room_name)
        self.assertEqual(units[0].amount, Decimal("109.00"))
        self.assertEqual(units[1].amount, Decimal("92.65"))

        self.assertEqual(
            Guest.objects.filter(reservation=reservation, name="Kurt Meeus").count(),
            1,
        )
        self.assertEqual(
            Guest.objects.filter(reservation=reservation, name="Kris Meeus").count(),
            1,
        )
        self.assertEqual(
            Guest.objects.filter(reservation=reservation, name=PLACEHOLDER_NAME).count(),
            2,
        )
