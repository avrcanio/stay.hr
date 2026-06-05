from datetime import date

from django.test import TestCase

from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.reservations.multi_room_guard import find_multi_room_inventory_gaps
from apps.tenants.models import Tenant


class MultiRoomGuardTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
        )
        self.unit_r1 = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="R1",
        )
        self.unit_r3 = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R3",
            name="R3",
        )

    def test_finds_units_count_gap(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 6, 25),
            check_out=date(2026, 6, 26),
            status=Reservation.Status.EXPECTED,
            booker_name="Jerzy Mochnik",
            booking_code="6748210815",
            units_count=2,
            import_source="channex",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_r3,
            room_name="R3",
        )
        gaps = find_multi_room_inventory_gaps(tenant=self.tenant, from_date=date(2026, 6, 1))
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["booking_code"], "6748210815")

    def test_no_gap_when_fully_mapped(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 6, 25),
            check_out=date(2026, 6, 26),
            status=Reservation.Status.EXPECTED,
            booker_name="Jerzy Mochnik",
            booking_code="6748210815",
            units_count=2,
            import_source="booking_pdf",
        )
        for idx, unit in enumerate((self.unit_r1, self.unit_r3)):
            ReservationUnit.objects.create(
                tenant=self.tenant,
                reservation=reservation,
                unit=unit,
                sort_order=idx,
                room_name=unit.code,
            )
        gaps = find_multi_room_inventory_gaps(tenant=self.tenant, from_date=date(2026, 6, 1))
        self.assertEqual(gaps, [])
