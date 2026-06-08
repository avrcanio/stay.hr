from django.test import SimpleTestCase

from apps.reservations.nationality_display import (
    apply_reservation_country_to_guest_if_empty,
    guest_nationality_iso2,
    iso3_to_iso2,
    normalize_country_iso2,
)


class NationalityDisplayTests(SimpleTestCase):
    def test_iso3_to_iso2_pol(self):
        self.assertEqual(iso3_to_iso2("POL"), "PL")

    def test_normalize_country_iso3(self):
        self.assertEqual(normalize_country_iso2("POL"), "PL")
        self.assertEqual(normalize_country_iso2("DEU"), "DE")
        self.assertEqual(normalize_country_iso2("HRV"), "HR")

    def test_normalize_country_iso2(self):
        self.assertEqual(normalize_country_iso2("PL"), "PL")
        self.assertEqual(normalize_country_iso2("DE"), "DE")
        self.assertEqual(normalize_country_iso2("RO"), "RO")

    def test_guest_nationality_ro(self):
        from unittest.mock import Mock

        guest = Mock()
        guest.nationality = "RO"
        guest.document_country_iso2 = "RO"
        guest.document_country_iso3 = "ROU"
        self.assertEqual(guest_nationality_iso2(guest), "RO")

    def test_invalid_truncated_iso2_rejected(self):
        self.assertEqual(normalize_country_iso2("PO"), "")

    def test_guest_nationality_falls_back_to_document_iso3(self):
        from unittest.mock import Mock

        guest = Mock()
        guest.nationality = "PO"
        guest.document_country_iso2 = ""
        guest.document_country_iso3 = "POL"
        self.assertEqual(guest_nationality_iso2(guest), "PL")

    def test_apply_reservation_country_to_guest_if_empty(self):
        from unittest.mock import Mock

        primary = Mock()
        primary.is_primary = True
        primary.nationality = "DE"
        primary.document_country_iso2 = "DE"
        primary.document_country_iso3 = ""

        guest = Mock()
        guest.nationality = ""
        guest.document_country_iso2 = ""
        guest.document_country_iso3 = ""

        reservation = Mock()
        reservation.booker_country = "DE"
        reservation.guests.all.return_value = [primary, guest]

        fields = apply_reservation_country_to_guest_if_empty(
            guest,
            reservation=reservation,
        )
        self.assertEqual(fields, ["nationality", "document_country_iso2"])
        self.assertEqual(guest.nationality, "DE")
        self.assertEqual(guest.document_country_iso2, "DE")
