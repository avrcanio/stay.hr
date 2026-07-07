from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.document_intake_context import DocumentIntakeContext
from apps.reservations.document_intake_service import apply_document_intake_job
from apps.reservations.models import (
    DocumentIntakeImage,
    DocumentIntakeJob,
    DocumentIntakeJobStatus,
    Guest,
    Reservation,
)
from apps.tenants.models import Tenant


class DocumentIntakePartialApplyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita", default_language="hr")
        self.property = Property.objects.create(tenant=self.tenant, name="Uzorita", slug="uzorita")
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Gabriele Boettcher",
            adults_count=2,
            check_in=date(2026, 6, 19),
            check_out=date(2026, 6, 21),
            status=Reservation.Status.EXPECTED,
        )
        self.primary = Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Gabriele",
            last_name="Boettcher",
            name="Gabriele Boettcher",
            is_primary=True,
        )
        self.second = Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Novi",
            last_name="gost",
            name="Novi gost",
        )
        self.job = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            status=DocumentIntakeJobStatus.DONE,
            ocr_result={
                "persons": [
                    {
                        "given_names": "Gabriele",
                        "surnames": "Boettcher",
                        "document_number": "L3H8V4JW1",
                        "document_type": "national_id",
                        "front_image_index": 0,
                        "back_image_index": 1,
                        "nationality": "DEU",
                        "date_of_birth": "1980-01-01",
                        "date_of_expiry": "2030-01-01",
                        "sex": "F",
                    },
                ],
            },
            matches=[
                {
                    "person_index": 0,
                    "auto_apply": True,
                    "guest_id": self.primary.pk,
                    "reservation_id": self.reservation.pk,
                    "guest_name": "Gabriele Boettcher",
                },
            ],
        )
        for i in range(2):
            DocumentIntakeImage.objects.create(
                tenant=self.tenant,
                job=self.job,
                image=SimpleUploadedFile(f"img{i}.jpg", b"fake", content_type="image/jpeg"),
                sort_order=i,
            )

    @patch("apps.reservations.document_intake_service.crop_face_jpeg", return_value=None)
    def test_partial_apply_one_of_two_adults_stays_done(self, _mock_crop):
        applied = apply_document_intake_job(
            DocumentIntakeContext.from_job(self.job),
            whatsapp_reply=False,
            allow_partial=True,
        )
        self.job.refresh_from_db()
        self.assertEqual(len(applied), 1)
        self.assertEqual(self.job.status, DocumentIntakeJobStatus.DONE)
        self.assertEqual(len(self.job.applied_result), 1)
        self.assertEqual(self.job.applied_result[0]["guest_id"], self.primary.pk)
