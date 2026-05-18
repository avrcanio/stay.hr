from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class ReceptionAPITests(TestCase):
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
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="ext-1",
            booking_code="BK-1",
            check_in=date(2026, 5, 10),
            check_out=date(2026, 5, 15),
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
        self.guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Marko",
            last_name="Marković",
            is_primary=True,
        )
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_health_unauthenticated(self):
        response = self.client.get("/api/v1/reception/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_timeline_requires_token(self):
        response = self.client.get("/api/v1/reception/reservations/")
        self.assertEqual(response.status_code, 403)

    def test_timeline_list(self):
        response = self.client.get("/api/v1/reception/reservations/", **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["id"], self.reservation.id)
        self.assertEqual(row["check_in_date"], "2026-05-10")
        self.assertEqual(row["check_out_date"], "2026-05-15")
        self.assertEqual(row["total_amount"], "120.00")
        self.assertEqual(row["room_name"], "Soba 101")
        self.assertEqual(len(row["guests"]), 1)

    def test_reservation_detail_and_patch_status(self):
        detail = self.client.get(
            f"/api/v1/reception/reservations/{self.reservation.id}/",
            **self.auth,
        )
        self.assertEqual(detail.status_code, 200)

        patch = self.client.patch(
            f"/api/v1/reception/reservations/{self.reservation.id}/",
            {"status": Reservation.Status.CHECKED_IN},
            format="json",
            **self.auth,
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()["status"], Reservation.Status.CHECKED_IN)

    def test_create_guest(self):
        response = self.client.post(
            f"/api/v1/reception/reservations/{self.reservation.id}/guests/",
            {"first_name": "Petra", "last_name": "Petrić"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["first_name"], "Petra")

    def test_document_scan_ingest(self):
        response = self.client.post(
            f"/api/v1/reception/reservations/{self.reservation.id}/guests/{self.guest.id}/document-scan/",
            {
                "metapodaci": {"metoda_ocitanja": "NFC", "tip_dokumenta": "passport"},
                "podaci_gosta": {
                    "ime": "Marko",
                    "prezime": "Marković",
                    "broj_dokumenta": "P1234567",
                },
                "sirovi_mrz": "P<HRVMARKO<<MARKOVIC",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scan_status"], "ok")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.document_number, "P1234567")

    @patch("apps.api.reception_views.submit_guest_checkin")
    def test_evisitor_submit(self, mock_submit):
        from apps.reservations.models import EvisitorSubmission
        from django.utils import timezone
        import uuid

        mock_submit.return_value = EvisitorSubmission(
            tenant=self.tenant,
            guest=self.guest,
            registration_id=uuid.uuid4(),
            status="sent",
            submitted_at=timezone.now(),
            created_at=timezone.now(),
        )
        response = self.client.post(
            f"/api/v1/reception/reservations/{self.reservation.id}/guests/{self.guest.id}/evisitor-submit/",
            {},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        mock_submit.assert_called_once()

    def test_read_scope_blocks_write(self):
        read_only_app, read_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Read only",
            scopes=["reception:read"],
        )
        response = self.client.patch(
            f"/api/v1/reception/reservations/{self.reservation.id}/",
            {"status": Reservation.Status.CHECKED_IN},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {read_token}",
        )
        self.assertEqual(response.status_code, 403)
