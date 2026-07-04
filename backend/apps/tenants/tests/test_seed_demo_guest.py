from __future__ import annotations

import io
import json
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.integrations.evisitor.config import EvisitorRuntimeConfig
from apps.integrations.evisitor.mapper import build_check_in_payload
from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant


class SeedDemoGuestCommandTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="demo",
            name="Demo",
            timezone="Europe/Zagreb",
            default_language="hr",
        )
        self.prop = Property.objects.create(
            tenant=self.tenant,
            slug="demo",
            name="Demo Property",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.prop,
            code="STD-01",
            name="Standard Double",
        )
        self.config = EvisitorRuntimeConfig(
            enabled=True,
            env="test",
            base_url="https://test.evisitor.hr/test/rest",
            username="user",
            password="pass",
            api_key="key",
            facility_code="12345",
            default_stay_time_from="15:00",
            default_stay_time_until="10:00",
            default_arrival_organisation="01",
            default_offered_service_type="01",
            default_payment_category="01",
        )

    def test_creates_reservation_and_guest(self):
        stdout = io.StringIO()
        call_command("seed_demo_guest", stdout=stdout)

        reservation = Reservation.objects.get(booking_code="MOCK-EVISITOR-001")
        self.assertEqual(reservation.property_id, self.prop.pk)
        self.assertEqual(reservation.status, Reservation.Status.EXPECTED)
        today = timezone.localdate()
        self.assertEqual(reservation.check_in, today)
        self.assertEqual(reservation.check_out, today + timedelta(days=2))

        guests = list(Guest.objects.filter(reservation=reservation))
        self.assertEqual(len(guests), 1)
        guest = guests[0]
        self.assertTrue(guest.is_primary)
        self.assertEqual(guest.sex, "M")
        self.assertEqual(guest.date_of_birth, date(1990, 1, 1))
        self.assertEqual(guest.document_number, "L1234567")
        self.assertEqual(guest.address, "Berlin, Grad Berlin")

        output = stdout.getvalue()
        self.assertIn(f"guest_id={guest.pk}", output)

    def test_idempotent_second_run(self):
        call_command("seed_demo_guest")
        call_command("seed_demo_guest")

        self.assertEqual(
            Reservation.objects.filter(booking_code="MOCK-EVISITOR-001").count(),
            1,
        )
        reservation = Reservation.objects.get(booking_code="MOCK-EVISITOR-001")
        self.assertEqual(Guest.objects.filter(reservation=reservation).count(), 1)

    @patch("apps.integrations.evisitor.mapper.iso2_to_iso3", return_value="DEU")
    def test_build_check_in_payload_passes(self, _mock_iso):
        call_command("seed_demo_guest")
        guest = Guest.objects.get(
            reservation__booking_code="MOCK-EVISITOR-001",
            is_primary=True,
        )
        payload = build_check_in_payload(
            guest,
            config=self.config,
            registration_id=uuid4(),
        )
        self.assertEqual(payload["TouristName"], "Test")
        self.assertEqual(payload["TouristSurname"], "Guest")

    def test_json_output(self):
        stdout = io.StringIO()
        call_command("seed_demo_guest", json=True, stdout=stdout)

        payload = json.loads(stdout.getvalue().strip())
        guest = Guest.objects.get(pk=payload["guest_id"])
        self.assertEqual(payload["booking_code"], "MOCK-EVISITOR-001")
        self.assertEqual(payload["reservation_id"], guest.reservation_id)
