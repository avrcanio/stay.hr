from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from apps.integrations.models import UnitAvailabilityBlock
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import PUBLIC_BOOKING_SCOPES, ApiApplication, Tenant


class PublicAvailabilityAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.unit_r1 = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="R1",
        )
        self.unit_r2 = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R2",
            name="R2",
        )
        _, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Booking web",
            scopes=PUBLIC_BOOKING_SCOPES,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_token}")

    def _availability(self, from_date: str, to_date: str):
        return self.client.get(
            "/api/v1/public/availability",
            {
                "from": from_date,
                "to": to_date,
                "property": "uzorita",
            },
        )

    def _unit_blocks(self, response, unit_id: int) -> list[dict]:
        for unit in response.data["units"]:
            if unit["unit_id"] == unit_id:
                return unit["blocked_periods"]
        return []

    def test_returns_200(self):
        response = self._availability("2026-05-27", "2026-05-28")
        self.assertEqual(response.status_code, 200, response.content)

    def test_expected_reservation_blocks_only_assigned_unit(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BLOCKR1",
            check_in=date(2026, 5, 27),
            check_out=date(2026, 5, 31),
            status=Reservation.Status.EXPECTED,
            booker_name="Guest",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_r1,
            sort_order=0,
            room_name="R1",
        )

        response = self._availability("2026-05-27", "2026-05-28")
        self.assertEqual(response.status_code, 200)

        r1_blocks = self._unit_blocks(response, self.unit_r1.id)
        r2_blocks = self._unit_blocks(response, self.unit_r2.id)
        self.assertEqual(len(r1_blocks), 1)
        self.assertEqual(r1_blocks[0]["booking_code"], "BLOCKR1")
        self.assertEqual(r1_blocks[0]["status"], "expected")
        self.assertEqual(r2_blocks, [])

    def test_manual_block_included(self):
        UnitAvailabilityBlock.objects.create(
            tenant=self.tenant,
            unit=self.unit_r2,
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            smoobu_booking_id="smoobu-block-1",
        )

        response = self._availability("2026-06-01", "2026-06-03")
        self.assertEqual(response.status_code, 200)

        r2_blocks = self._unit_blocks(response, self.unit_r2.id)
        self.assertEqual(len(r2_blocks), 1)
        self.assertEqual(r2_blocks[0]["booking_code"], "smoobu-block-1")
        self.assertEqual(r2_blocks[0]["status"], "blocked")

    def test_canceled_reservation_does_not_block(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="CANCELED1",
            check_in=date(2026, 5, 27),
            check_out=date(2026, 5, 31),
            status=Reservation.Status.CANCELED,
            booker_name="Guest",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_r1,
            sort_order=0,
            room_name="R1",
        )

        response = self._availability("2026-05-27", "2026-05-28")
        self.assertEqual(self._unit_blocks(response, self.unit_r1.id), [])

    def test_pending_reservation_does_not_block(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="PENDING1",
            check_in=date(2026, 5, 27),
            check_out=date(2026, 5, 31),
            status=Reservation.Status.PENDING,
            booker_name="Guest",
            source="api",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_r1,
            sort_order=0,
            room_name="R1",
        )

        response = self._availability("2026-05-27", "2026-05-28")
        self.assertEqual(self._unit_blocks(response, self.unit_r1.id), [])
