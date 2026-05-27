from django.test import SimpleTestCase

from apps.billing.services.country_names_hr import country_display_name_hr


class CountryNamesHrTests(SimpleTestCase):
    def test_iso2_to_croatian_name(self):
        self.assertEqual(country_display_name_hr("BE"), "Belgija")
        self.assertEqual(country_display_name_hr("HR"), "Hrvatska")
        self.assertEqual(country_display_name_hr("de"), "Njemačka")

    def test_unknown_iso2_returns_code(self):
        self.assertEqual(country_display_name_hr("ZZ"), "ZZ")

    def test_full_name_passthrough(self):
        self.assertEqual(country_display_name_hr("Some Country"), "Some Country")
