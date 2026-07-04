from unittest.mock import patch

import fitz
from django.core.files.base import ContentFile
from django.test import TestCase

from apps.reservations.document_intake_pdf import (
    JPEG_MIME,
    expand_bytes_for_ocr,
    remap_ocr_indices_to_source,
    source_indices_to_ocr_slots,
)
from apps.reservations.document_intake_service import process_document_intake_job
from apps.reservations.models import (
    DocumentIntakeImage,
    DocumentIntakeJob,
    DocumentIntakeJobStatus,
)
from apps.tenants.models import Tenant


def _content_file(data: bytes, name: str):
    return ContentFile(data, name=name)


def _make_pdf(page_count: int = 2) -> bytes:
    doc = fitz.open()
    try:
        for page_num in range(page_count):
            page = doc.new_page()
            page.insert_text((72, 72), f"Test document page {page_num + 1}")
        return doc.tobytes()
    finally:
        doc.close()


class ExpandBytesForOcrTests(TestCase):
    def test_jpeg_pass_through(self):
        jpeg = b"\xff\xd8\xff fake-jpeg"
        ocr_bytes, ocr_mimes, ocr_to_source = expand_bytes_for_ocr(
            [jpeg],
            ["image/jpeg"],
        )
        self.assertEqual(ocr_bytes, [jpeg])
        self.assertEqual(ocr_mimes, ["image/jpeg"])
        self.assertEqual(ocr_to_source, [0])

    def test_pdf_expands_to_jpeg_pages(self):
        pdf = _make_pdf(page_count=3)
        ocr_bytes, ocr_mimes, ocr_to_source = expand_bytes_for_ocr(
            [pdf],
            ["application/pdf"],
        )
        self.assertEqual(len(ocr_bytes), 3)
        self.assertTrue(all(m == JPEG_MIME for m in ocr_mimes))
        self.assertEqual(ocr_to_source, [0, 0, 0])
        self.assertTrue(all(data.startswith(b"\xff\xd8") for data in ocr_bytes))

    def test_mixed_pdf_and_jpeg(self):
        jpeg = b"\xff\xd8\xff fake-jpeg"
        pdf = _make_pdf(page_count=2)
        ocr_bytes, ocr_mimes, ocr_to_source = expand_bytes_for_ocr(
            [jpeg, pdf],
            ["image/jpeg", "application/pdf"],
        )
        self.assertEqual(len(ocr_bytes), 3)
        self.assertEqual(ocr_to_source, [0, 1, 1])
        self.assertEqual(ocr_mimes[0], "image/jpeg")
        self.assertEqual(ocr_mimes[1], JPEG_MIME)
        self.assertEqual(ocr_mimes[2], JPEG_MIME)

    def test_remap_ocr_indices_to_source(self):
        ocr_result = {
            "images": [{"index": 0, "side": "front"}, {"index": 2, "side": "back"}],
            "persons": [{"front_image_index": 0, "back_image_index": 2}],
        }
        remapped = remap_ocr_indices_to_source(ocr_result, [0, 1, 1])
        self.assertEqual(remapped["images"][0]["index"], 0)
        self.assertEqual(remapped["images"][1]["index"], 1)
        self.assertEqual(remapped["persons"][0]["front_image_index"], 0)
        self.assertEqual(remapped["persons"][0]["back_image_index"], 1)

    def test_source_indices_to_ocr_slots(self):
        slots = source_indices_to_ocr_slots([1], [0, 1, 1, 2])
        self.assertEqual(slots, [1, 2])


class MixedPdfJpegOcrIntegrationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="PDF Test", slug="pdf-test")

    @patch("apps.reservations.document_intake_service.ocr_configured", return_value=True)
    @patch("apps.reservations.document_intake_service.run_document_batch_ocr")
    def test_process_job_expands_pdf_before_ocr(self, mock_ocr, _configured):
        mock_ocr.return_value = {
            "images": [{"index": 0, "side": "front"}, {"index": 1, "side": "back"}],
            "persons": [
                {
                    "given_names": "Ana",
                    "surnames": "Test",
                    "front_image_index": 0,
                    "back_image_index": 1,
                }
            ],
        }

        job = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            status=DocumentIntakeJobStatus.QUEUED,
            device_id="test",
        )
        DocumentIntakeImage.objects.create(
            tenant=self.tenant,
            job=job,
            sort_order=0,
            image=_content_file(b"\xff\xd8\xff jpeg", "0.jpg"),
        )
        DocumentIntakeImage.objects.create(
            tenant=self.tenant,
            job=job,
            sort_order=1,
            image=_content_file(_make_pdf(page_count=2), "1.pdf"),
        )

        process_document_intake_job(job.pk)
        job.refresh_from_db()

        self.assertEqual(job.status, DocumentIntakeJobStatus.DONE)
        call_kwargs = mock_ocr.call_args.kwargs
        self.assertEqual(len(call_kwargs["image_bytes_list"]), 3)
        self.assertTrue(all(m == JPEG_MIME for m in call_kwargs["mime_types"][1:]))
        self.assertEqual(job.ocr_result["persons"][0]["front_image_index"], 0)
        self.assertEqual(job.ocr_result["persons"][0]["back_image_index"], 1)
        self.assertEqual(job.ocr_result["_preprocess"]["pdf_expand_source_count"], 2)
        self.assertEqual(job.ocr_result["_preprocess"]["pdf_expand_ocr_count"], 3)

    @patch("apps.reservations.document_intake_service.ocr_configured", return_value=True)
    @patch("apps.reservations.document_intake_service.run_orphan_document_ocr")
    @patch("apps.reservations.document_intake_service.run_document_batch_ocr")
    def test_orphan_pass_uses_expanded_pdf_slots(self, mock_batch_ocr, mock_orphan_ocr, _configured):
        mock_batch_ocr.return_value = {
            "images": [{"index": 0, "side": "front"}],
            "persons": [
                {
                    "given_names": "Ana",
                    "surnames": "Test",
                    "front_image_index": 0,
                }
            ],
        }
        mock_orphan_ocr.return_value = {
            "images": [{"index": 1, "side": "back"}],
            "persons": [
                {
                    "given_names": "Ana",
                    "surnames": "Test",
                    "back_image_index": 1,
                }
            ],
        }

        job = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            reservation=_reservation(self.tenant),
            status=DocumentIntakeJobStatus.QUEUED,
            device_id="test",
        )
        DocumentIntakeImage.objects.create(
            tenant=self.tenant,
            job=job,
            sort_order=0,
            image=_content_file(b"\xff\xd8\xff jpeg", "0.jpg"),
        )
        DocumentIntakeImage.objects.create(
            tenant=self.tenant,
            job=job,
            sort_order=1,
            image=_content_file(_make_pdf(page_count=2), "1.pdf"),
        )

        process_document_intake_job(job.pk)

        orphan_call = mock_orphan_ocr.call_args.kwargs
        self.assertEqual(orphan_call["orphan_indices"], [1, 2])
        self.assertEqual(len(orphan_call["image_bytes_list"]), 3)


def _reservation(tenant: Tenant):
    from datetime import date

    from apps.properties.models import Property
    from apps.reservations.models import Reservation

    prop = Property.objects.create(tenant=tenant, name="Hotel", slug="hotel")
    return Reservation.objects.create(
        tenant=tenant,
        property=prop,
        check_in=date(2026, 7, 4),
        check_out=date(2026, 7, 6),
        adults_count=2,
        status=Reservation.Status.EXPECTED,
    )
