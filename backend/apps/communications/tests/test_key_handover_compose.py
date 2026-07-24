from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.communications.key_handover_compose import (
    render_key_handover_guide,
    reservation_key_handover_labels,
)
from apps.properties.guest_info import effective_unit_key_label, normalize_guest_info
from apps.properties.models import Property, SelfServiceMode, Unit
from apps.properties.uzorita_guest_info import UZORITA_GUEST_INFO
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant


class KeyHandoverComposeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="KH Tenant", slug="kh-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="KH Property",
            slug="kh-property",
            guest_info=UZORITA_GUEST_INFO,
            address="Ul. bana Josipa Jelačića 58, 22000 Šibenik",
            check_in_time=time(15, 0),
            self_service_mode=SelfServiceMode.ALWAYS,
            after_hours_contact_phone="+385998388513",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R3",
            name="Room 3",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="KH-001",
            check_in=date(2026, 7, 21),
            check_out=date(2026, 7, 23),
            adults_count=1,
            booker_name="Mehmet Test",
            amount=Decimal("100.00"),
            booker_country="DE",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
            sort_order=0,
        )

    def test_effective_unit_key_label_strips_room_prefix(self):
        self.assertEqual(effective_unit_key_label(self.unit), "3")

    def test_reservation_key_handover_labels(self):
        key_label, room_code = reservation_key_handover_labels(self.reservation)
        self.assertEqual(room_code, "R3")
        self.assertEqual(key_label, "3")

    def test_render_key_handover_guide_includes_key_and_room(self):
        body = render_key_handover_guide(self.reservation)
        self.assertIn("R3", body)
        self.assertIn("3", body)
        self.assertIn("7:30", body)

    def test_uzorita_guest_info_guide_normalized_with_steps(self):
        info = normalize_guest_info(UZORITA_GUEST_INFO)
        guide = info["guide"]
        self.assertIn("intro", guide["sections"])
        self.assertEqual(len(guide["steps"]), 8)
        self.assertTrue(
            guide["steps"][0]["image"].startswith("assets/guest-portal/uzorita/steps/")
        )
        self.assertIn("fr", guide["steps"][0]["caption"])

    def test_compose_key_handover_guide_command_dry_run(self):
        out = StringIO()
        call_command(
            "compose_key_handover_guide",
            reservation_id=self.reservation.pk,
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("self_service_mode: always", text)
        self.assertIn("R3", text)
        self.assertIn("Not sent", text)
