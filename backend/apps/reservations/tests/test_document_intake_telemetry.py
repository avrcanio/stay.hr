from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image

from apps.properties.models import Property
from apps.reservations.document_intake_context import DocumentIntakeContext
from apps.reservations.document_intake_failure_reasons import OCRFailureReason, reason_label
from apps.reservations.document_intake_service import process_document_intake_job
from apps.reservations.document_intake_telemetry import (
    PIPELINE_VERSION,
    QUALITY_MODEL_ID,
    TELEMETRY_SCHEMA_VERSION,
    _derive_summary_reasons,
    aggregate_telemetry_kpis,
    attach_document_intake_telemetry,
    build_document_intake_telemetry,
)
from apps.reservations.models import (
    DocumentIntakeImage,
    DocumentIntakeJob,
    DocumentIntakeJobStatus,
    Guest,
    Reservation,
)
from apps.tenants.models import Tenant


def _jpeg_bytes(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color="white").save(buf, format="JPEG")
    return buf.getvalue()


def _telemetry_without_computed_at(telemetry: dict) -> dict:
    result = dict(telemetry)
    result.pop("computed_at", None)
    return result


class DocumentIntakeFailureReasonTests(TestCase):
    def test_reason_label_hr(self):
        self.assertEqual(reason_label(OCRFailureReason.NO_MRZ), "MRZ nije prepoznat")

    def test_reason_label_unknown_string(self):
        self.assertEqual(reason_label("custom_reason"), "custom_reason")


class DocumentIntakeTelemetryPureTests(TestCase):
    def test_telemetry_schema_version_and_model(self):
        telemetry = build_document_intake_telemetry(
            ocr_result={"persons": [], "images": []},
            image_count=0,
        )
        self.assertEqual(telemetry["schema_version"], TELEMETRY_SCHEMA_VERSION)
        self.assertEqual(telemetry["quality_model"], QUALITY_MODEL_ID)
        self.assertEqual(telemetry["pipeline_version"], PIPELINE_VERSION)
        self.assertIn("computed_at", telemetry)

    def test_summary_reasons_derived_from_children(self):
        summary = _derive_summary_reasons(
            images_telemetry=[{"reasons": ["no_mrz"]}],
            persons_telemetry=[{"reasons": ["unknown_person"]}],
            job_reasons=["ocr_under_extracted"],
        )
        self.assertEqual(
            summary,
            sorted({"no_mrz", "unknown_person", "ocr_under_extracted"}),
        )
        self.assertIn("unknown_person", summary)

    def test_unknown_person_reason(self):
        telemetry = build_document_intake_telemetry(
            ocr_result={
                "persons": [{"given_names": "", "surnames": "", "document_type": "national_id"}],
                "images": [],
            },
            image_count=0,
        )
        person_reasons = telemetry["persons"][0]["reasons"]
        self.assertIn(OCRFailureReason.UNKNOWN_PERSON.value, person_reasons)
        self.assertIn(OCRFailureReason.UNKNOWN_PERSON.value, telemetry["summary_reasons"])

    def test_no_mrz_on_back(self):
        telemetry = build_document_intake_telemetry(
            ocr_result={
                "persons": [
                    {
                        "given_names": "Ana",
                        "surnames": "Test",
                        "document_type": "national_id",
                        "front_image_index": 0,
                        "back_image_index": 1,
                    }
                ],
                "images": [
                    {"index": 0, "side": "front"},
                    {"index": 1, "side": "back", "mrz_lines": []},
                ],
            },
            image_count=2,
        )
        self.assertIn(OCRFailureReason.NO_MRZ.value, telemetry["summary_reasons"])

    def test_image_too_small(self):
        small = _jpeg_bytes(600, 900)
        large = _jpeg_bytes(1200, 1600)
        telemetry = build_document_intake_telemetry(
            ocr_result={
                "persons": [],
                "images": [{"index": 0, "side": "front"}, {"index": 1, "side": "back"}],
            },
            image_bytes_list=[small, large],
            image_count=2,
        )
        self.assertIn(OCRFailureReason.IMAGE_TOO_SMALL.value, telemetry["images"][0]["reasons"])
        resolution = telemetry["quality_components"]["resolution"]
        self.assertEqual(resolution["below_threshold_count"], 1)
        self.assertEqual(resolution["threshold_px"], 800)
        self.assertEqual(resolution["min_edge_px"], 600)

    def test_quality_score_deterministic(self):
        ocr_result = {
            "persons": [
                {
                    "given_names": "Ana",
                    "surnames": "Test",
                    "document_type": "national_id",
                    "front_image_index": 0,
                    "back_image_index": 1,
                    "mrz_lines": ["LINE1", "LINE2"],
                }
            ],
            "images": [
                {"index": 0, "side": "front"},
                {"index": 1, "side": "back", "mrz_lines": ["LINE1", "LINE2"]},
            ],
        }
        kwargs = {
            "ocr_result": ocr_result,
            "image_bytes_list": [_jpeg_bytes(1200, 1200), _jpeg_bytes(1200, 1200)],
            "image_count": 2,
            "matches": [{"person_index": 0, "auto_apply": True}],
        }
        first = _telemetry_without_computed_at(build_document_intake_telemetry(**kwargs))
        second = _telemetry_without_computed_at(build_document_intake_telemetry(**kwargs))
        self.assertEqual(first, second)

    def test_unknown_future_fields_are_preserved(self):
        ocr_result = {
            "persons": [],
            "images": [],
            "_telemetry": {"future": "abc", "schema_version": 0},
        }
        telemetry = build_document_intake_telemetry(ocr_result=ocr_result, image_count=0)
        merged = attach_document_intake_telemetry(ocr_result, telemetry)
        self.assertEqual(merged["_telemetry"]["future"], "abc")
        self.assertEqual(merged["_telemetry"]["schema_version"], TELEMETRY_SCHEMA_VERSION)

    def test_failed_job_telemetry(self):
        telemetry = build_document_intake_telemetry(
            ocr_result={},
            job_status=DocumentIntakeJobStatus.FAILED,
        )
        self.assertIn(OCRFailureReason.OCR_FAILED.value, telemetry["summary_reasons"])
        self.assertEqual(telemetry["quality_score"], 0)

    def test_aggregate_reason_distribution(self):
        tenant = Tenant.objects.create(name="Telemetry", slug="telemetry-kpi")
        job_a = DocumentIntakeJob.objects.create(
            tenant=tenant,
            status=DocumentIntakeJobStatus.DONE,
            processed_at=timezone.now(),
            ocr_result={
                "_telemetry": {
                    "quality_model": QUALITY_MODEL_ID,
                    "pipeline_version": PIPELINE_VERSION,
                    "quality_score": 80,
                    "summary_reasons": ["no_mrz", "unknown_person"],
                    "persons": [{"reasons": ["unknown_person"]}],
                    "job_metrics": {
                        "auto_apply_count": 1,
                        "match_count": 2,
                        "unknown_person_count": 1,
                        "ocr_under_extracted": True,
                    },
                }
            },
        )
        job_b = DocumentIntakeJob.objects.create(
            tenant=tenant,
            status=DocumentIntakeJobStatus.DONE,
            processed_at=timezone.now(),
            ocr_result={
                "_telemetry": {
                    "quality_model": QUALITY_MODEL_ID,
                    "pipeline_version": PIPELINE_VERSION,
                    "quality_score": 60,
                    "summary_reasons": ["no_mrz"],
                    "persons": [{"reasons": []}],
                    "job_metrics": {
                        "auto_apply_count": 0,
                        "match_count": 1,
                        "unknown_person_count": 0,
                        "ocr_under_extracted": False,
                    },
                }
            },
        )
        kpis = aggregate_telemetry_kpis([job_a, job_b], quality_model=QUALITY_MODEL_ID)
        self.assertEqual(kpis["processed"], 2)
        self.assertEqual(kpis["top_reasons"][0], ("no_mrz", 2))
        self.assertEqual(kpis["top_reasons"][1], ("unknown_person", 1))


class DocumentIntakeTelemetryIntegrationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Telemetry Int", slug="telemetry-int")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Hotel",
            slug="hotel-telemetry",
            address="Test",
        )

    @patch("apps.reservations.document_intake_service.ocr_configured", return_value=True)
    @patch("apps.reservations.document_intake_service.run_document_batch_ocr")
    def test_process_job_persists_telemetry(self, mock_ocr, _configured):
        canonical_persons = [
            {
                "given_names": "Ana",
                "surnames": "Test",
                "document_type": "national_id",
                "front_image_index": 0,
                "back_image_index": 1,
                "mrz_lines": ["LINE1", "LINE2"],
            }
        ]
        mock_ocr.return_value = {
            "images": [
                {"index": 0, "side": "front"},
                {"index": 1, "side": "back", "mrz_lines": ["LINE1", "LINE2"]},
            ],
            "persons": canonical_persons,
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
            image=ContentFile(_jpeg_bytes(1200, 1200), name="0.jpg"),
        )
        DocumentIntakeImage.objects.create(
            tenant=self.tenant,
            job=job,
            sort_order=1,
            image=ContentFile(_jpeg_bytes(1200, 1200), name="1.jpg"),
        )

        process_document_intake_job(DocumentIntakeContext.from_job(job))
        job.refresh_from_db()

        self.assertEqual(job.status, DocumentIntakeJobStatus.DONE)
        person = job.ocr_result["persons"][0]
        self.assertEqual(person["given_names"], "Ana")
        self.assertEqual(person["surnames"], "Test")
        self.assertEqual(person["mrz_lines"], ["LINE1", "LINE2"])
        telemetry = job.ocr_result.get("_telemetry") or {}
        self.assertEqual(telemetry.get("schema_version"), TELEMETRY_SCHEMA_VERSION)
        self.assertIn("quality_score", telemetry)
        self.assertIn("summary_reasons", telemetry)

    @patch("apps.reservations.document_intake_service.ocr_configured", return_value=False)
    def test_process_job_failed_path_persists_telemetry(self, _configured):
        job = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            status=DocumentIntakeJobStatus.QUEUED,
            device_id="test",
        )
        DocumentIntakeImage.objects.create(
            tenant=self.tenant,
            job=job,
            sort_order=0,
            image=ContentFile(_jpeg_bytes(1200, 1200), name="0.jpg"),
        )

        process_document_intake_job(DocumentIntakeContext.from_job(job))
        job.refresh_from_db()

        self.assertEqual(job.status, DocumentIntakeJobStatus.FAILED)
        telemetry = job.ocr_result.get("_telemetry") or {}
        self.assertIn(OCRFailureReason.OCR_FAILED.value, telemetry.get("summary_reasons", []))

    def test_completeness_telemetry_with_reservation(self):
        today = timezone.now().date()
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=today,
            check_out=today + timedelta(days=2),
            status=Reservation.Status.EXPECTED,
            adults_count=2,
            persons_count=2,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Ana",
            last_name="Test",
            name="Ana Test",
            is_primary=True,
        )

        telemetry = build_document_intake_telemetry(
            ocr_result={
                "persons": [
                    {
                        "given_names": "Ana",
                        "surnames": "Test",
                        "document_type": "national_id",
                        "front_image_index": 0,
                    }
                ],
                "images": [{"index": 0, "side": "front"}, {"index": 1, "side": "back"}],
            },
            image_count=2,
            reservation=reservation,
            matches=[{"person_index": 0, "auto_apply": True, "guest_id": 1}],
        )
        self.assertIn(OCRFailureReason.OCR_UNDER_EXTRACTED.value, telemetry["summary_reasons"])
        self.assertIn(OCRFailureReason.UNASSIGNED_IMAGES.value, telemetry["summary_reasons"])
