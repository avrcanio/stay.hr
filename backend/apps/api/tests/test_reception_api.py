import io
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, IdRecognitionSample, Reservation, ReservationUnit
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

    @patch("apps.core.tasks.notify_reservation_status_changed.delay")
    def test_reservation_detail_and_patch_status(self, mock_notify_status):
        detail = self.client.get(
            f"/api/v1/reception/reservations/{self.reservation.id}/",
            **self.auth,
        )
        self.assertEqual(detail.status_code, 200)

        patch = self.client.patch(
            f"/api/v1/reception/reservations/{self.reservation.id}/",
            {"status": Reservation.Status.CHECKED_IN},
            format="json",
            HTTP_AUTHORIZATION=self.auth["HTTP_AUTHORIZATION"],
            HTTP_X_INSTALLATION_ID="tablet-a-uuid",
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()["status"], Reservation.Status.CHECKED_IN)
        mock_notify_status.assert_called_once_with(
            self.reservation.id,
            Reservation.Status.EXPECTED,
            Reservation.Status.CHECKED_IN,
            "tablet-a-uuid",
        )

    def test_create_guest(self):
        response = self.client.post(
            f"/api/v1/reception/reservations/{self.reservation.id}/guests/",
            {"first_name": "Petra", "last_name": "Petrić"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["first_name"], "Petra")

    @override_settings(MEDIA_ROOT="/tmp/stay_test_media")
    def test_id_scan_sample_upload(self):
        # Minimal valid JPEG (1x1)
        jpeg_bytes = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
            b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
            b"\x1c $.\x27 ,#\x1c\x1c(7),01444\x1f\x27=9=82<.7\xff\xc0\x00\x0b\x08"
            b"\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01"
            b"\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07"
            b"\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05"
            b"\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"
            b"\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18"
            b"\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86"
            b"\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6"
            b"\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6"
            b"\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5"
            b"\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00"
            b"\x08\x01\x01\x00\x00?\x00\xfb\xd5\xdb\x20\xff\xd9"
        )
        image = SimpleUploadedFile("sample.jpg", jpeg_bytes, content_type="image/jpeg")
        response = self.client.post(
            f"/api/v1/reception/reservations/{self.reservation.id}/guests/{self.guest.id}/id-scan-samples/",
            {
                "image": image,
                "document_type": "passport",
                "source": "mrz_plus",
                "raw_mrz": "P<HRVMARKO<<MARKOVIC",
                "device_id": "tablet-test",
            },
            format="multipart",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        sample_id = response.json()["sample_id"]
        sample = IdRecognitionSample.objects.get(pk=sample_id)
        self.assertEqual(sample.tenant_id, self.tenant.id)
        self.assertEqual(sample.source, "mrz_plus")
        self.assertTrue(sample.image.name)
        self.assertTrue(io.BytesIO(sample.image.read()).getvalue())

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

    def test_sync_versions(self):
        response = self.client.get(
            "/api/v1/reception/sync-versions/?year=2026",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("reservations", data)
        self.assertIn("rooms", data)
        self.assertIn("2026", data["statistics"])
        self.assertEqual(len(data["reservations"]), 16)
        etag = response["ETag"]
        self.assertTrue(etag.startswith('W/"'))
        self.assertTrue(etag.endswith('"'))

        cached = self.client.get(
            "/api/v1/reception/sync-versions/?year=2026",
            HTTP_IF_NONE_MATCH=etag,
            **self.auth,
        )
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached.content, b"")

        self.reservation.status = Reservation.Status.CHECKED_IN
        self.reservation.save(update_fields=["status", "updated_at"])

        after_change = self.client.get(
            "/api/v1/reception/sync-versions/?year=2026",
            HTTP_IF_NONE_MATCH=etag,
            **self.auth,
        )
        self.assertEqual(after_change.status_code, 200)
        self.assertNotEqual(after_change["ETag"], etag)

    def test_monthly_statistics(self):
        self.reservation.status = Reservation.Status.CHECKED_IN
        self.reservation.save(update_fields=["status", "updated_at"])

        response = self.client.get(
            "/api/v1/reception/statistics/monthly/?year=2026",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["year"], 2026)
        self.assertEqual(data["comparison_year"], 2025)
        self.assertEqual(len(data["months"]), 12)
        may = next(m for m in data["months"] if m["month"] == 5)
        self.assertEqual(may["current"]["revenue"], "120.00")

    def test_monthly_statistics_invalid_year(self):
        response = self.client.get(
            "/api/v1/reception/statistics/monthly/?year=abc",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)

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
