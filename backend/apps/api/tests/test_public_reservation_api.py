from django.test import TestCase
from rest_framework.test import APIClient

from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import PUBLIC_BOOKING_SCOPES, ApiApplication, Tenant


class PublicReservationCreateAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="101",
            name="Soba 101",
        )
        _, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Booking web",
            scopes=PUBLIC_BOOKING_SCOPES,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_token}")

    def test_create_reservation_assigns_unit(self):
        response = self.client.post(
            "/api/v1/public/reservations",
            {
                "property_slug": "uzorita",
                "unit_id": self.unit.id,
                "check_in": "2026-07-01",
                "check_out": "2026-07-05",
                "booker_name": "Ana Anić",
                "booker_email": "ana@example.com",
                "guests": [{"first_name": "Ana", "last_name": "Anić"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(booking_code=response.data["booking_code"])
        units = list(ReservationUnit.objects.filter(reservation=reservation))
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].unit_id, self.unit.id)
        self.assertEqual(units[0].room_name, "Soba 101")

    def test_rejects_unknown_unit(self):
        response = self.client.post(
            "/api/v1/public/reservations",
            {
                "property_slug": "uzorita",
                "unit_id": 99999,
                "check_in": "2026-07-01",
                "check_out": "2026-07-05",
                "booker_name": "Ana Anić",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("unit_id", response.data)

    def test_requires_unit_id(self):
        response = self.client.post(
            "/api/v1/public/reservations",
            {
                "property_slug": "uzorita",
                "check_in": "2026-07-01",
                "check_out": "2026-07-05",
                "booker_name": "Ana Anić",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("unit_id", response.data)
