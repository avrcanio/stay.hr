from datetime import date

from django.test import TestCase

from apps.integrations.channex.reservation_availability_service import (
    UZORITA_WHOLE_PROPERTY_UNIT_CODES,
    qualifies_for_whole_property_sync,
)
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant


class WholePropertyAvailabilityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
        )
        self.units = {}
        for code in UZORITA_WHOLE_PROPERTY_UNIT_CODES:
            self.units[code] = Unit.objects.create(
                tenant=self.tenant,
                property=self.property,
                code=code,
                name=code,
            )

    def test_qualifies_with_two_core_rooms(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 7, 24),
            check_out=date(2026, 7, 25),
            status=Reservation.Status.EXPECTED,
            booker_name="Susanne Mayer",
            units_count=4,
        )
        for code in ("R1", "R3"):
            ReservationUnit.objects.create(
                tenant=self.tenant,
                reservation=reservation,
                unit=self.units[code],
                room_name=code,
            )
        self.assertTrue(qualifies_for_whole_property_sync(reservation))

    def test_does_not_qualify_single_room(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 7, 24),
            check_out=date(2026, 7, 25),
            status=Reservation.Status.EXPECTED,
            booker_name="Pierre",
            units_count=1,
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.units["R1"],
            room_name="R1",
        )
        self.assertFalse(qualifies_for_whole_property_sync(reservation))
