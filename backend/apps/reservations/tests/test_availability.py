from datetime import date

from django.test import TestCase

from apps.integrations.models import UnitAvailabilityDay
from apps.properties.models import Property, Unit
from apps.reservations.availability import unit_blocked_nights, validate_unit_available_for_booking
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant


class ValidateUnitAvailableForBookingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="demo", name="Demo")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="demo",
            name="Demo",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="R1",
        )

    def test_allows_booking_when_no_ari_rows(self):
        validate_unit_available_for_booking(
            self.tenant,
            self.unit,
            date(2026, 6, 1),
            date(2026, 6, 3),
        )

    def test_allows_booking_when_ari_open(self):
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 6, 1),
            availability=1,
        )
        validate_unit_available_for_booking(
            self.tenant,
            self.unit,
            date(2026, 6, 1),
            date(2026, 6, 2),
        )

    def test_rejects_booking_when_ari_closed(self):
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 6, 1),
            availability=0,
        )
        with self.assertRaises(ValueError) as ctx:
            validate_unit_available_for_booking(
                self.tenant,
                self.unit,
                date(2026, 6, 1),
                date(2026, 6, 2),
            )
        self.assertIn("not available", str(ctx.exception))

    def test_rejects_when_any_night_in_stay_is_closed(self):
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 6, 2),
            availability=0,
        )
        with self.assertRaises(ValueError):
            validate_unit_available_for_booking(
                self.tenant,
                self.unit,
                date(2026, 6, 1),
                date(2026, 6, 3),
            )

    def test_unit_blocked_nights_lists_individual_closed_nights(self):
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 6, 3),
            availability=0,
        )
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 6, 5),
            availability=0,
        )
        blocked = unit_blocked_nights(
            self.tenant,
            self.unit.id,
            date(2026, 6, 1),
            date(2026, 6, 8),
        )
        self.assertEqual(blocked, [date(2026, 6, 3), date(2026, 6, 5)])

    def test_exclude_reservation_id_allows_move_on_same_unit(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 5, 24),
            check_out=date(2026, 5, 27),
            status=Reservation.Status.EXPECTED,
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit,
        )

        with self.assertRaises(ValueError):
            validate_unit_available_for_booking(
                self.tenant,
                self.unit,
                date(2026, 5, 24),
                date(2026, 5, 27),
            )

        validate_unit_available_for_booking(
            self.tenant,
            self.unit,
            date(2026, 5, 28),
            date(2026, 5, 30),
            exclude_reservation_id=reservation.id,
        )

        blocked = unit_blocked_nights(
            self.tenant,
            self.unit.id,
            date(2026, 5, 24),
            date(2026, 6, 1),
            exclude_reservation_id=reservation.id,
        )
        self.assertEqual(blocked, [])

    def test_exclude_reservation_id_skips_ari_on_current_stay_nights(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 5, 24),
            check_out=date(2026, 5, 27),
            status=Reservation.Status.EXPECTED,
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit,
        )
        for night in (date(2026, 5, 24), date(2026, 5, 25), date(2026, 5, 26)):
            UnitAvailabilityDay.objects.create(
                tenant=self.tenant,
                unit=self.unit,
                date=night,
                availability=0,
            )

        with self.assertRaises(ValueError):
            validate_unit_available_for_booking(
                self.tenant,
                self.unit,
                date(2026, 5, 24),
                date(2026, 5, 27),
            )

        validate_unit_available_for_booking(
            self.tenant,
            self.unit,
            date(2026, 5, 24),
            date(2026, 5, 27),
            exclude_reservation_id=reservation.id,
        )

        blocked = unit_blocked_nights(
            self.tenant,
            self.unit.id,
            date(2026, 5, 24),
            date(2026, 5, 28),
            exclude_reservation_id=reservation.id,
        )
        self.assertEqual(blocked, [])

    def test_exclude_reservation_id_skips_ari_on_current_stay_nights(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 5, 24),
            check_out=date(2026, 5, 27),
            status=Reservation.Status.EXPECTED,
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit,
        )
        for night in (date(2026, 5, 24), date(2026, 5, 25), date(2026, 5, 26)):
            UnitAvailabilityDay.objects.create(
                tenant=self.tenant,
                unit=self.unit,
                date=night,
                availability=0,
            )

        with self.assertRaises(ValueError):
            validate_unit_available_for_booking(
                self.tenant,
                self.unit,
                date(2026, 5, 24),
                date(2026, 5, 27),
            )

        validate_unit_available_for_booking(
            self.tenant,
            self.unit,
            date(2026, 5, 24),
            date(2026, 5, 27),
            exclude_reservation_id=reservation.id,
        )

        blocked = unit_blocked_nights(
            self.tenant,
            self.unit.id,
            date(2026, 5, 24),
            date(2026, 5, 28),
            exclude_reservation_id=reservation.id,
        )
        self.assertEqual(blocked, [])
