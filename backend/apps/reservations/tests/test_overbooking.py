from datetime import date, datetime

from django.test import TestCase
from django.utils import timezone

from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.reservations.overbooking import find_conflicts, pick_incumbent_and_conflicting
from apps.reservations.reservation_units import resync_unit_assignments
from apps.tenants.models import Tenant


class OverbookingIncumbentTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita-overbooking")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.r3 = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R3",
            name="R3",
        )

    def _create_reservation(
        self,
        *,
        external_id: str,
        booker_name: str,
        check_in: date,
        check_out: date,
        booked_at: datetime | None = None,
    ) -> Reservation:
        return Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id=external_id,
            booking_code=external_id,
            check_in=check_in,
            check_out=check_out,
            booker_name=booker_name,
            status=Reservation.Status.EXPECTED,
            booked_at=booked_at,
        )

    def test_sauvagere_vlemminx_scenario(self):
        incumbent = self._create_reservation(
            external_id="6541736653",
            booker_name="Sauvagere",
            check_in=date(2026, 5, 21),
            check_out=date(2026, 5, 24),
        )
        conflicting = self._create_reservation(
            external_id="5272845192",
            booker_name="Vlemminx",
            check_in=date(2026, 5, 23),
            check_out=date(2026, 5, 24),
        )
        for reservation in (incumbent, conflicting):
            ReservationUnit.objects.create(
                tenant=self.tenant,
                reservation=reservation,
                unit=self.r3,
                room_name="Deluxe Triple Room R3",
            )

        conflicts = find_conflicts(tenant=self.tenant)
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertEqual(conflict.unit, self.r3)
        self.assertEqual(conflict.overlap_from, date(2026, 5, 23))
        self.assertEqual(conflict.overlap_to, date(2026, 5, 24))
        self.assertEqual(conflict.incumbent, incumbent)
        self.assertEqual(conflict.conflicting, conflicting)

    def test_same_check_in_uses_booked_at_tie_breaker(self):
        check_in = date(2026, 6, 1)
        check_out = date(2026, 6, 3)
        earlier = self._create_reservation(
            external_id="111",
            booker_name="Earlier Booker",
            check_in=check_in,
            check_out=check_out,
            booked_at=timezone.make_aware(datetime(2026, 5, 1, 10, 0)),
        )
        later = self._create_reservation(
            external_id="222",
            booker_name="Later Booker",
            check_in=check_in,
            check_out=check_out,
            booked_at=timezone.make_aware(datetime(2026, 5, 2, 10, 0)),
        )

        picked_incumbent, picked_conflicting = pick_incumbent_and_conflicting(earlier, later)
        self.assertEqual(picked_incumbent, earlier)
        self.assertEqual(picked_conflicting, later)

        for reservation in (earlier, later):
            ReservationUnit.objects.create(
                tenant=self.tenant,
                reservation=reservation,
                unit=self.r3,
                room_name="R3",
            )

        conflicts = find_conflicts(tenant=self.tenant)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].incumbent, earlier)
        self.assertEqual(conflicts[0].conflicting, later)

    def test_non_overlapping_reservations_are_ignored(self):
        first = self._create_reservation(
            external_id="333",
            booker_name="First",
            check_in=date(2026, 5, 1),
            check_out=date(2026, 5, 3),
        )
        second = self._create_reservation(
            external_id="444",
            booker_name="Second",
            check_in=date(2026, 5, 3),
            check_out=date(2026, 5, 5),
        )
        for reservation in (first, second):
            ReservationUnit.objects.create(
                tenant=self.tenant,
                reservation=reservation,
                unit=self.r3,
                room_name="R3",
            )

        self.assertEqual(find_conflicts(tenant=self.tenant), [])

    def test_from_date_filters_out_past_conflicts(self):
        incumbent = self._create_reservation(
            external_id="555",
            booker_name="Past Incumbent",
            check_in=date(2026, 5, 1),
            check_out=date(2026, 5, 10),
        )
        conflicting = self._create_reservation(
            external_id="666",
            booker_name="Past Conflicting",
            check_in=date(2026, 5, 5),
            check_out=date(2026, 5, 8),
        )
        for reservation in (incumbent, conflicting):
            ReservationUnit.objects.create(
                tenant=self.tenant,
                reservation=reservation,
                unit=self.r3,
                room_name="R3",
            )

        self.assertEqual(
            find_conflicts(tenant=self.tenant, from_date=date(2026, 5, 21)),
            [],
        )


class ResyncUnitAssignmentsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita-resync")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.r1 = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="R1",
        )
        self.r3 = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R3",
            name="R3",
        )

    def test_resync_updates_misassigned_unit(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5213202593",
            booking_code="5213202593",
            check_in=date(2026, 5, 22),
            check_out=date(2026, 5, 23),
            booker_name="Hoferica",
            status=Reservation.Status.EXPECTED,
        )
        row = ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.r1,
            room_name="Deluxe Triple Room",
        )

        changes = resync_unit_assignments(tenant=self.tenant)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].old_unit_id, self.r1.id)
        self.assertEqual(changes[0].new_unit_id, self.r3.id)

        row.refresh_from_db()
        self.assertEqual(row.unit_id, self.r3.id)

    def test_resync_dry_run_does_not_persist(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="777",
            booking_code="777",
            check_in=date(2026, 5, 22),
            check_out=date(2026, 5, 23),
            booker_name="Dry Run",
            status=Reservation.Status.EXPECTED,
        )
        row = ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.r1,
            room_name="Deluxe Triple Room",
        )

        changes = resync_unit_assignments(tenant=self.tenant, dry_run=True)
        self.assertEqual(len(changes), 1)
        row.refresh_from_db()
        self.assertEqual(row.unit_id, self.r1.id)
