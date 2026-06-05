from django.test import SimpleTestCase

from apps.reservations.nationality_display import (
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

    def test_invalid_truncated_iso2_rejected(self):
        self.assertEqual(normalize_country_iso2("PO"), "")

    def test_guest_nationality_falls_back_to_document_iso3(self):
        from unittest.mock import Mock

        guest = Mock()
        guest.nationality = "PO"
        guest.document_country_iso2 = ""
        guest.document_country_iso3 = "POL"
        self.assertEqual(guest_nationality_iso2(guest), "PL")
