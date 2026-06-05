from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.integrations.channex.booking_room_mismatch import (
    MULTI_ROOM_SUSPECT_NOTE,
    CHANNEX_EMPTY_ROOMS_NOTE,
    detect_channex_room_mismatch,
    flag_channex_ingest_room_warnings,
    flag_channex_room_mismatch,
    should_preserve_units_on_channex_ingest,
)
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant


class BookingRoomMismatchTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
        )
        self.unit_r6 = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R6",
            name="R6",
        )

    def _reservation(self, **overrides):
        defaults = {
            "tenant": self.tenant,
            "property": self.property,
            "check_in": date(2026, 7, 24),
            "check_out": date(2026, 7, 25),
            "status": Reservation.Status.EXPECTED,
            "booker_name": "Susanne Mayer",
            "booking_code": "5796838012",
            "units_count": 4,
            "import_source": "channex",
        }
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    def test_should_preserve_when_channex_under_reports_on_update(self):
        reservation = self._reservation(units_count=2)
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_r6,
            room_name="R6",
        )
        unit_r1 = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="R1",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=unit_r1,
            sort_order=1,
            room_name="R1",
        )
        self.assertTrue(
            should_preserve_units_on_channex_ingest(
                reservation=reservation,
                created=False,
                channex_rooms_count=1,
                incoming_status=Reservation.Status.EXPECTED,
            )
        )

    def test_should_not_preserve_on_first_ingest(self):
        reservation = self._reservation(units_count=1)
        self.assertFalse(
            should_preserve_units_on_channex_ingest(
                reservation=reservation,
                created=True,
                channex_rooms_count=1,
                incoming_status=Reservation.Status.EXPECTED,
            )
        )

    def test_detect_multi_room_single_mapped_unit(self):
        reservation = self._reservation(units_count=4)
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_r6,
            room_name="R6",
        )
        issues = detect_channex_room_mismatch(reservation, channex_rooms_count=1)
        self.assertTrue(any("multi-room" in issue.lower() or "mapped" in issue for issue in issues))

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_flag_appends_note_and_notifies(self, mock_push):
        reservation = self._reservation(units_count=2)
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_r6,
            room_name="R6",
        )
        issues = flag_channex_room_mismatch(reservation, channex_rooms_count=1)
        self.assertTrue(issues)
        reservation.refresh_from_db()
        self.assertIn("CHANNEX_ROOMS_MISMATCH:", reservation.notes)
        mock_push.assert_called_once()

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_ingest_warning_empty_channex_rooms(self, mock_push):
        reservation = self._reservation(units_count=0, adults_count=2)
        issues = flag_channex_ingest_room_warnings(
            reservation,
            channex_rooms_count=0,
            adults_count=2,
        )
        self.assertTrue(issues)
        reservation.refresh_from_db()
        self.assertIn(CHANNEX_EMPTY_ROOMS_NOTE, reservation.notes)
        mock_push.assert_called_once()

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_ingest_warning_multi_room_suspect(self, mock_push):
        reservation = self._reservation(units_count=1, adults_count=4)
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_r6,
            room_name="R6",
        )
        issues = flag_channex_ingest_room_warnings(
            reservation,
            channex_rooms_count=1,
            adults_count=4,
        )
        self.assertTrue(issues)
        reservation.refresh_from_db()
        self.assertIn(MULTI_ROOM_SUSPECT_NOTE, reservation.notes)
        mock_push.assert_called_once()
