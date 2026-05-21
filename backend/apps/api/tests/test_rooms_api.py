from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class RoomsAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.other_tenant = Tenant.objects.create(name="Other", slug="other")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.other_property = Property.objects.create(
            tenant=self.other_tenant,
            name="Other",
            slug="other",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="101",
            name="Soba 101",
        )
        self.other_unit = Unit.objects.create(
            tenant=self.other_tenant,
            property=self.other_property,
            code="201",
            name="Other 201",
        )
        _, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="ext-cal-1",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            status=Reservation.Status.CHECKED_IN,
            booker_name="Ana Anić",
            amount=Decimal("300.00"),
            nights_count=4,
            persons_count=2,
            adults_count=2,
            children_count=0,
            payment_status="Booking.com",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
            room_name="Soba 101",
            sort_order=0,
        )
        self.guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Marko",
            last_name="Marković",
            nationality="de",
            is_primary=True,
        )
        self.other_reservation = Reservation.objects.create(
            tenant=self.other_tenant,
            property=self.other_property,
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.CHECKED_IN,
            booker_name="Secret",
        )
        ReservationUnit.objects.create(
            tenant=self.other_tenant,
            reservation=self.other_reservation,
            unit=self.other_unit,
            room_name="Other 201",
            sort_order=0,
        )
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_rooms_list_requires_token(self):
        response = self.client.get("/api/v1/rooms/rooms/")
        self.assertEqual(response.status_code, 403)

    def test_rooms_list(self):
        response = self.client.get("/api/v1/rooms/rooms/?lang=hr", **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], self.unit.id)
        self.assertEqual(data[0]["code"], "101")
        self.assertTrue(data[0]["is_active"])

    def test_room_calendar(self):
        response = self.client.get(
            f"/api/v1/rooms/rooms/{self.unit.id}/calendar/"
            "?from=2026-01-01&to=2026-12-31&lang=hr",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["id"], self.reservation.id)
        self.assertEqual(row["check_in_date"], "2026-06-01")
        self.assertEqual(row["check_out_date"], "2026-06-05")
        self.assertEqual(row["status"], Reservation.Status.CHECKED_IN)
        self.assertEqual(row["primary_guest_name"], "Marko Marković")
        self.assertEqual(row["primary_guest_nationality_iso2"], "DE")
        self.assertEqual(row["room_name"], "Soba 101")
        self.assertEqual(row["nights_count"], 4)
        self.assertEqual(row["persons_count"], 2)
        self.assertEqual(row["adults_count"], 2)
        self.assertEqual(row["children_count"], 0)
        self.assertEqual(row["guests_count"], 1)
        self.assertEqual(row["payment_status"], "Booking.com")
        self.assertEqual(row["payment_status_key"], "booking")

    def test_calendar_unknown_unit_404(self):
        response = self.client.get(
            f"/api/v1/rooms/rooms/{self.other_unit.id}/calendar/"
            "?from=2026-01-01&to=2026-12-31",
            **self.auth,
        )
        self.assertEqual(response.status_code, 404)

    def test_tenant_isolation_on_calendar(self):
        response = self.client.get(
            f"/api/v1/rooms/rooms/{self.unit.id}/calendar/"
            "?from=2026-01-01&to=2026-12-31",
            **self.auth,
        )
        ids = {row["id"] for row in response.json()}
        self.assertNotIn(self.other_reservation.id, ids)
