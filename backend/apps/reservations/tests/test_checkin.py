from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from apps.properties.models import Property, Unit
from apps.reservations.checkin import (
    CheckInBlockedError,
    get_check_in_block_reason,
    validate_reservation_check_in,
)
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant


class CheckInValidationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita-ci")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita-ci",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="101",
            name="Soba 101",
        )
        self.arrival = date(2026, 5, 26)
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-CI",
            check_in=self.arrival,
            check_out=date(2026, 5, 30),
            status=Reservation.Status.EXPECTED,
            booker_name="Ana Anić",
            amount=Decimal("120.00"),
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
            room_name="Soba 101",
            sort_order=0,
        )

    def _mock_today(self, day: date):
        tz = ZoneInfo("Europe/Zagreb")
        fixed = datetime(day.year, day.month, day.day, 10, 0, tzinfo=tz)
        return patch(
            "apps.reservations.checkin.property_local_now",
            return_value=fixed,
        )

    def test_check_in_allowed_on_arrival_date_when_room_free(self):
        with self._mock_today(self.arrival):
            validate_reservation_check_in(self.reservation, tenant=self.tenant)

    def test_check_in_rejected_before_arrival_date(self):
        with self._mock_today(date(2026, 5, 25)):
            with self.assertRaises(CheckInBlockedError) as ctx:
                validate_reservation_check_in(self.reservation, tenant=self.tenant)
        self.assertEqual(ctx.exception.code, "wrong_date")

    def test_check_in_allowed_after_arrival_date_when_room_free(self):
        with self._mock_today(date(2026, 5, 28)):
            validate_reservation_check_in(self.reservation, tenant=self.tenant)

    def test_check_in_rejected_when_room_occupied(self):
        other = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-OTHER",
            check_in=date(2026, 5, 20),
            check_out=date(2026, 5, 28),
            status=Reservation.Status.CHECKED_IN,
            booker_name="Petra Petrić",
            amount=Decimal("90.00"),
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=other,
            unit=self.unit,
            room_name="Soba 101",
            sort_order=0,
        )

        with self._mock_today(self.arrival):
            with self.assertRaises(CheckInBlockedError) as ctx:
                validate_reservation_check_in(self.reservation, tenant=self.tenant)
        self.assertEqual(ctx.exception.code, "room_occupied")

    def test_check_in_allowed_when_other_guest_stale_checked_in(self):
        other = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-STALE",
            check_in=date(2026, 5, 20),
            check_out=date(2026, 5, 25),
            status=Reservation.Status.CHECKED_IN,
            booker_name="Stale Guest",
            amount=Decimal("90.00"),
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=other,
            unit=self.unit,
            room_name="Soba 101",
            sort_order=0,
        )

        with self._mock_today(self.arrival):
            validate_reservation_check_in(self.reservation, tenant=self.tenant)

    def test_check_in_allowed_when_other_reservation_expected_on_same_room(self):
        other = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-EXPECTED",
            check_in=date(2026, 5, 24),
            check_out=date(2026, 5, 28),
            status=Reservation.Status.EXPECTED,
            booker_name="Kris Meeus",
            amount=Decimal("90.00"),
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=other,
            unit=self.unit,
            room_name="Soba 101",
            sort_order=0,
        )

        with self._mock_today(self.arrival):
            validate_reservation_check_in(self.reservation, tenant=self.tenant)

    def test_check_in_rejected_without_assigned_unit(self):
        bare = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-NOUNIT",
            check_in=self.arrival,
            check_out=date(2026, 5, 30),
            status=Reservation.Status.EXPECTED,
            booker_name="No Unit",
            amount=Decimal("50.00"),
        )
        with self._mock_today(self.arrival):
            with self.assertRaises(CheckInBlockedError) as ctx:
                validate_reservation_check_in(bare, tenant=self.tenant)
        self.assertEqual(ctx.exception.code, "no_unit")

    def test_get_check_in_block_reason_none_when_allowed(self):
        with self._mock_today(self.arrival):
            self.assertIsNone(get_check_in_block_reason(self.reservation, tenant=self.tenant))

    def test_get_check_in_block_reason_returns_error_object(self):
        with self._mock_today(date(2026, 5, 25)):
            block = get_check_in_block_reason(self.reservation, tenant=self.tenant)
        self.assertIsNotNone(block)
        self.assertEqual(block.code, "wrong_date")
