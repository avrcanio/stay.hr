from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.properties.models import Property, Unit
from apps.reservations.guest_slots import PLACEHOLDER_FIRST, PLACEHOLDER_LAST
from apps.reservations.models import DocumentIntakeJobStatus, Guest, Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


def _tiny_jpeg(name: str = "doc.jpg") -> SimpleUploadedFile:
    buf = BytesIO()
    Image.new("RGB", (40, 40), color=(200, 180, 160)).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    MEDIA_ROOT="/tmp/stay_test_media",
)
class DocumentIntakeAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Luxury Room Uzorita",
            slug="uzorita",
            address="Test",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="Deluxe King Room R1",
        )
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5036489024",
            booking_code="5036489024",
            check_in="2026-06-04",
            check_out="2026-06-06",
            status=Reservation.Status.EXPECTED,
            booker_name="Hans Fischer",
            booker_email="hans@example.com",
            booker_phone="+49 170 1234567",
            amount=Decimal("180.15"),
            adults_count=2,
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
        )
        self.primary = Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Hans",
            last_name="Fischer",
            name="Hans Fischer",
            is_primary=True,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name=PLACEHOLDER_FIRST,
            last_name=PLACEHOLDER_LAST,
            name="Novi gost",
            is_primary=False,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_token}")
        self.base = "/api/v1/reception/document-intake"

    @patch("apps.reservations.document_intake_service.run_document_batch_ocr")
    def test_batch_process_apply_updates_guest(self, mock_ocr):
        mock_ocr.return_value = {
            "images": [
                {
                    "index": 0,
                    "side": "front",
                    "mrz_lines": [],
                    "ocr_text": "REPUBLIKA HRVATSKA\nHans Fischer",
                }
            ],
            "persons": [
                {
                    "given_names": "Hans",
                    "surnames": "Fischer",
                    "document_number": "L01X00T47",
                    "nationality": "DEU",
                    "date_of_birth": "1980-05-01",
                    "date_of_expiry": "2030-05-01",
                    "sex": "M",
                    "address": "Markdorf, Teststr. 1",
                    "document_type": "national_id",
                    "front_image_index": 0,
                    "back_image_index": None,
                    "mrz_lines": ["IDD<<FISCHER<<HANS"],
                    "face_bbox": {"x": 0.05, "y": 0.12, "w": 0.35, "h": 0.45},
                }
            ],
        }

        batch = self.client.post(
            f"{self.base}/batch/",
            {"files": [_tiny_jpeg()]},
            format="multipart",
        )
        self.assertEqual(batch.status_code, 201)
        job_id = batch.json()["job_id"]

        process = self.client.post(f"{self.base}/jobs/{job_id}/process/")
        self.assertEqual(process.status_code, 200)
        body = process.json()
        self.assertEqual(body["status"], DocumentIntakeJobStatus.DONE)
        self.assertEqual(len(body["matches"]), 1)
        self.assertTrue(body["matches"][0]["auto_apply"])
        self.assertIn("ocr_summary", body)
        self.assertIn("Hans", body["ocr_summary"])

        apply = self.client.post(f"{self.base}/jobs/{job_id}/apply/", {}, format="json")
        self.assertEqual(apply.status_code, 200)
        self.assertEqual(apply.json()["status"], DocumentIntakeJobStatus.APPLIED)
        self.assertEqual(len(apply.json()["applied"]), 1)

        self.primary.refresh_from_db()
        self.assertEqual(self.primary.document_number, "L01X00T47")
        self.assertEqual(self.primary.first_name, "Hans")

    @patch("apps.reservations.document_intake_service.run_document_batch_ocr")
    def test_name_match_auto_apply_despite_other_unfilled_slots(self, mock_ocr):
        """Single name match must auto-apply even when other reservations have empty slots."""
        from datetime import date

        mock_ocr.return_value = {
            "images": [{"index": 0, "side": "front", "mrz_lines": [], "ocr_text": ""}],
            "persons": [
                {
                    "given_names": "Hans",
                    "surnames": "Fischer",
                    "document_number": "L01X00T47",
                    "nationality": "DEU",
                    "document_type": "national_id",
                    "front_image_index": 0,
                }
            ],
        }

        for day_offset, booker in ((0, "Other A"), (1, "Other B")):
            other = Reservation.objects.create(
                tenant=self.tenant,
                property=self.property,
                external_id=f"other-{day_offset}",
                booking_code=f"other-{day_offset}",
                check_in=date(2026, 6, 4 + day_offset),
                check_out=date(2026, 6, 6 + day_offset),
                status=Reservation.Status.EXPECTED,
                booker_name=booker,
            )
            Guest.objects.create(
                tenant=self.tenant,
                reservation=other,
                first_name=PLACEHOLDER_FIRST,
                last_name=PLACEHOLDER_LAST,
                name="Novi gost",
            )

        batch = self.client.post(
            f"{self.base}/batch/",
            {"files": [_tiny_jpeg()]},
            format="multipart",
        )
        job_id = batch.json()["job_id"]
        process = self.client.post(f"{self.base}/jobs/{job_id}/process/")
        body = process.json()

        self.assertEqual(body["status"], DocumentIntakeJobStatus.DONE)
        match = body["matches"][0]
        self.assertEqual(match["confidence"], "high")
        self.assertTrue(match["auto_apply"])
        self.assertEqual(match["reservation_id"], self.reservation.id)
        self.assertEqual(match["guest_id"], self.primary.id)
        self.assertEqual(len(match["candidates"]), 1)

    def test_batch_requires_files(self):
        res = self.client.post(f"{self.base}/batch/", {}, format="multipart")
        self.assertEqual(res.status_code, 400)
