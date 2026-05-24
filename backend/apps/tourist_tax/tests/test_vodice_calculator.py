from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.tourist_tax.management.commands.seed_vodice_tourist_tax import Command as VodiceSeedCommand
from apps.tourist_tax.models import TouristTaxAccommodationCategory, TouristTaxZone
from apps.tourist_tax.services.calculator import GuestAgeInput, calculate_tourist_tax
from apps.tourist_tax.management.commands.seed_sibenik_tourist_tax import Command as SibenikSeedCommand


class VodiceTouristTaxCalculatorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SibenikSeedCommand().handle()
        VodiceSeedCommand().handle()

    def setUp(self):
        self.zone = TouristTaxZone.objects.get(code="vodice")
        self.room = TouristTaxAccommodationCategory.objects.get(code="room")

    def test_main_season_two_adults_two_children_one_night(self):
        result = calculate_tourist_tax(
            check_in=date(2026, 7, 15),
            check_out=date(2026, 7, 16),
            guests=[
                GuestAgeInput(age_years=35),
                GuestAgeInput(age_years=40),
                GuestAgeInput(age_years=8),
                GuestAgeInput(age_years=10),
            ],
            zone=self.zone,
            category=self.room,
        )

        self.assertEqual(result.nights, 1)
        self.assertEqual(result.total, Decimal("3.60"))
        self.assertEqual(result.lines[0].base_rate, Decimal("1.80"))
        self.assertEqual(result.lines[0].season_code, "main")

    def test_off_season_two_adults_two_children_one_night(self):
        result = calculate_tourist_tax(
            check_in=date(2026, 11, 15),
            check_out=date(2026, 11, 16),
            guests=[
                GuestAgeInput(age_years=35),
                GuestAgeInput(age_years=40),
                GuestAgeInput(age_years=8),
                GuestAgeInput(age_years=10),
            ],
            zone=self.zone,
            category=self.room,
        )

        self.assertEqual(result.nights, 1)
        self.assertEqual(result.total, Decimal("2.66"))
        self.assertEqual(result.lines[0].base_rate, Decimal("1.33"))
        self.assertEqual(result.lines[0].season_code, "off")
