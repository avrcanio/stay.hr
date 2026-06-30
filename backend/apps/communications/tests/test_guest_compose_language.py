from django.test import TestCase

from apps.communications.guest_compose_language import (
    compose_language_for_reservation,
    language_from_country,
)
from apps.properties.models import Property
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant


class GuestComposeLanguageTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita B&B",
            slug="uzorita",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="123",
            check_in="2026-06-05",
            check_out="2026-06-09",
            status=Reservation.Status.EXPECTED,
            booker_name="Test Guest",
        )

    def test_language_from_country_hr_balkan(self):
        for code in ("HR", "RS", "BA", "ME", "SI", "MK"):
            self.assertEqual(language_from_country(code), "hr")

    def test_language_from_country_de(self):
        for code in ("DE", "AT", "CH"):
            self.assertEqual(language_from_country(code), "de")

    def test_language_from_country_es(self):
        self.assertEqual(language_from_country("ES"), "es")
        self.assertEqual(language_from_country("MX"), "es")

    def test_language_from_country_fr(self):
        self.assertEqual(language_from_country("FR"), "fr")

    def test_language_from_country_default_en(self):
        self.assertEqual(language_from_country("US"), "en")

    def test_language_from_country_nl(self):
        self.assertEqual(language_from_country("NL"), "nl")

    def test_language_from_country_ro(self):
        self.assertEqual(language_from_country("RO"), "ro")

    def test_language_from_country_it(self):
        self.assertEqual(language_from_country("IT"), "it")

    def test_compose_language_api_override(self):
        self.reservation.booker_country = "DE"
        self.reservation.save(update_fields=["booker_country"])
        self.assertEqual(compose_language_for_reservation(self.reservation, "es"), "es")

    def test_compose_language_from_booker_country(self):
        self.reservation.booker_country = "DE"
        self.reservation.save(update_fields=["booker_country"])
        self.assertEqual(compose_language_for_reservation(self.reservation), "de")

    def test_compose_language_from_guest_nationality(self):
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Ana",
            last_name="Test",
            nationality="RS",
            is_primary=True,
        )
        self.assertEqual(compose_language_for_reservation(self.reservation), "hr")
