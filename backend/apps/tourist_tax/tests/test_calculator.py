from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant
from apps.tourist_tax.management.commands.seed_sibenik_tourist_tax import Command as SeedCommand
from apps.tourist_tax.models import (
    TouristTaxAccommodationCategory,
    TouristTaxOrdinance,
    TouristTaxZone,
)
from apps.tourist_tax.services.calculator import (
    GuestAgeInput,
    TouristTaxConfigError,
    TouristTaxValidationError,
    age_on,
    calculate_tourist_tax,
    calculate_tourist_tax_for_reservation,
    date_in_season,
)


class TouristTaxCalculatorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SeedCommand().handle()

    def setUp(self):
        self.ordinance = TouristTaxOrdinance.objects.get(code="sibenik")
        self.central_zone = TouristTaxZone.objects.get(code="sibenik-central")
        self.peripheral_zone = TouristTaxZone.objects.get(code="sibenik-peripheral")
        self.room = TouristTaxAccommodationCategory.objects.get(code="room")
        self.main_season = self.ordinance.seasons.get(code="main")
        self.off_season = self.ordinance.seasons.get(code="off")

    def test_main_season_central_zone_mixed_guests(self):
        result = calculate_tourist_tax(
            check_in=date(2026, 4, 15),
            check_out=date(2026, 4, 18),
            guests=[
                GuestAgeInput(date_of_birth=date(1990, 5, 1)),
                GuestAgeInput(date_of_birth=date(1985, 3, 12)),
                GuestAgeInput(date_of_birth=date(2012, 6, 1)),
                GuestAgeInput(date_of_birth=date(2018, 1, 20)),
            ],
            zone=self.central_zone,
            category=self.room,
        )

        self.assertEqual(result.nights, 3)
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.total, Decimal("13.95"))
        self.assertEqual(result.lines[0].night_total, Decimal("4.65"))
        self.assertEqual(result.lines[0].base_rate, Decimal("1.86"))
        self.assertEqual(result.lines[0].season_code, "main")

    def test_checkout_day_not_charged(self):
        one_night = calculate_tourist_tax(
            check_in=date(2026, 4, 15),
            check_out=date(2026, 4, 16),
            guests=[GuestAgeInput(age_years=30)],
            zone=self.central_zone,
            category=self.room,
        )
        with self.assertRaises(TouristTaxValidationError):
            calculate_tourist_tax(
                check_in=date(2026, 4, 15),
                check_out=date(2026, 4, 15),
                guests=[GuestAgeInput(age_years=30)],
                zone=self.central_zone,
                category=self.room,
            )

        self.assertEqual(one_night.nights, 1)
        self.assertEqual(one_night.total, Decimal("1.86"))

    def test_off_season_peripheral_zone(self):
        result = calculate_tourist_tax(
            check_in=date(2026, 11, 1),
            check_out=date(2026, 11, 3),
            guests=[GuestAgeInput(age_years=40)],
            zone=self.peripheral_zone,
            category=self.room,
        )

        self.assertEqual(result.nights, 2)
        self.assertEqual(result.total, Decimal("2.00"))
        self.assertEqual(result.lines[0].season_code, "off")
        self.assertEqual(result.lines[0].base_rate, Decimal("1.00"))

    def test_year_crossing_off_season(self):
        result = calculate_tourist_tax(
            check_in=date(2026, 12, 28),
            check_out=date(2027, 1, 3),
            guests=[GuestAgeInput(age_years=35)],
            zone=self.central_zone,
            category=self.room,
        )

        self.assertEqual(result.nights, 6)
        self.assertTrue(all(line.season_code == "off" for line in result.lines))
        self.assertEqual(result.total, Decimal("7.98"))

    def test_age_boundary_multipliers(self):
        cases = [
            (11, Decimal("0.00")),
            (12, Decimal("0.93")),
            (17, Decimal("0.93")),
            (18, Decimal("1.86")),
        ]
        for age_years, expected_amount in cases:
            with self.subTest(age_years=age_years):
                result = calculate_tourist_tax(
                    check_in=date(2026, 5, 1),
                    check_out=date(2026, 5, 2),
                    guests=[GuestAgeInput(age_years=age_years)],
                    zone=self.central_zone,
                    category=self.room,
                )
                self.assertEqual(result.total, expected_amount)

    def test_date_in_season_wraparound(self):
        winter_day = date(2026, 1, 15)
        summer_day = date(2026, 7, 15)
        self.assertTrue(date_in_season(winter_day, self.off_season))
        self.assertFalse(date_in_season(winter_day, self.main_season))
        self.assertTrue(date_in_season(summer_day, self.main_season))
        self.assertFalse(date_in_season(summer_day, self.off_season))

    def test_age_on_birthday(self):
        self.assertEqual(age_on(date(2026, 5, 1), date(2008, 5, 1)), 18)
        self.assertEqual(age_on(date(2026, 4, 30), date(2008, 5, 1)), 17)

    def test_missing_guest_age_raises(self):
        with self.assertRaises(TouristTaxValidationError):
            calculate_tourist_tax(
                check_in=date(2026, 4, 15),
                check_out=date(2026, 4, 16),
                guests=[GuestAgeInput()],
                zone=self.central_zone,
                category=self.room,
            )

    def test_calculate_for_reservation_requires_property_config(self):
        tenant = Tenant.objects.create(name="Test", slug="test-tax")
        prop = Property.objects.create(tenant=tenant, name="Test", slug="test-tax")
        reservation = Reservation.objects.create(
            tenant=tenant,
            property=prop,
            check_in=date(2026, 4, 15),
            check_out=date(2026, 4, 16),
            booker_name="Guest",
        )
        Guest.objects.create(
            tenant=tenant,
            reservation=reservation,
            first_name="Ana",
            last_name="Test",
            name="Ana Test",
            date_of_birth=date(1990, 1, 1),
            is_primary=True,
        )

        with self.assertRaises(TouristTaxConfigError):
            calculate_tourist_tax_for_reservation(reservation)

    def test_calculate_for_reservation_with_config(self):
        tenant = Tenant.objects.create(name="Uzorita test", slug="uzorita-tax")
        prop = Property.objects.create(
            tenant=tenant,
            name="Uzorita",
            slug="uzorita",
            tourist_tax_zone=self.central_zone,
            tourist_tax_category=self.room,
        )
        reservation = Reservation.objects.create(
            tenant=tenant,
            property=prop,
            check_in=date(2026, 4, 15),
            check_out=date(2026, 4, 18),
            booker_name="Guest",
        )
        Guest.objects.create(
            tenant=tenant,
            reservation=reservation,
            first_name="Ana",
            last_name="Test",
            name="Ana Test",
            date_of_birth=date(1990, 1, 1),
            nationality="HR",
            sex="F",
            is_primary=True,
        )
        Guest.objects.create(
            tenant=tenant,
            reservation=reservation,
            first_name="Marko",
            last_name="Test",
            name="Marko Test",
            date_of_birth=date(1985, 6, 1),
            nationality="HR",
            sex="M",
        )

        result = calculate_tourist_tax_for_reservation(reservation)
        self.assertEqual(result.nights, 3)
        self.assertEqual(result.total, Decimal("11.16"))
