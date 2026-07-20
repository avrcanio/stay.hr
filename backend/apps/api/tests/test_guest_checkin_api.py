from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.properties.models import Property
from apps.reservations.guest_checkin_orchestrator import GuestCheckInOrchestrator
from apps.reservations.models import (
    DocumentIntakeImage,
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    DocumentIntakeJobStatus,
    Guest,
    GuestCheckInSessionCreatedFrom,
    GuestCheckInSessionStatus,
    Reservation,
)
from apps.tenants.models import Tenant


class GuestCheckInPublicAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="API Tenant", slug="api-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="API Property",
            slug="api-property",
            guest_checkin_opens_days_before=0,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="API-001",
            check_in=timezone.localdate(),
            check_out=timezone.localdate() + timedelta(days=2),
            adults_count=1,
            booker_name="API Guest",
            amount=Decimal("100.00"),
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Novi",
            last_name="gost",
            name="Novi gost",
            is_primary=True,
        )
        ensured = GuestCheckInOrchestrator.ensure_session_and_link(
            self.reservation,
            created_from=GuestCheckInSessionCreatedFrom.EMAIL,
        )
        self.session = ensured.session
        self.token = str(self.session.token)

    def test_get_session_returns_readiness(self):
        url = reverse("public-guest-checkin-session", kwargs={"token": self.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], GuestCheckInSessionStatus.ACTIVE)
        self.assertEqual(data["required_slots"], 1)
        self.assertFalse(data["can_complete"])
        self.assertEqual(len(data["slots"]), 1)

    def test_get_progress_is_lightweight(self):
        url = reverse("public-guest-checkin-progress", kwargs={"token": self.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("effective_status", data)
        self.assertIn("can_complete", data)
        self.assertNotIn("booking_code", data)

    def test_patch_slot_autosaves_and_returns_readiness(self):
        url = reverse(
            "public-guest-checkin-slot",
            kwargs={"token": self.token, "position": 1},
        )
        response = self.client.patch(
            url,
            {
                "first_name": "Ana",
                "last_name": "Anić",
                "date_of_birth": "1990-01-15",
                "nationality": "HR",
                "sex": "female",
                "document_number": "12345678901",
                "document_type": "identity_card",
                "address": "Zagreb, Ulica 1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["effective_status"], "ready")
        self.assertTrue(data["can_complete"])
        self.assertEqual(data["slot"]["guest"]["first_name"], "Ana")

    def test_complete_requires_ready(self):
        url = reverse("public-guest-checkin-complete", kwargs={"token": self.token})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "not_ready")

    def test_complete_marks_session_completed(self):
        patch_url = reverse(
            "public-guest-checkin-slot",
            kwargs={"token": self.token, "position": 1},
        )
        self.client.patch(
            patch_url,
            {
                "first_name": "Ana",
                "last_name": "Anić",
                "date_of_birth": "1990-01-15",
                "nationality": "HR",
                "sex": "female",
                "document_number": "12345678901",
                "document_type": "identity_card",
                "address": "Zagreb, Ulica 1",
            },
            format="json",
        )
        complete_url = reverse("public-guest-checkin-complete", kwargs={"token": self.token})
        response = self.client.post(complete_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], GuestCheckInSessionStatus.COMPLETED)

        session_url = reverse("public-guest-checkin-session", kwargs={"token": self.token})
        blocked = self.client.get(session_url)
        self.assertEqual(blocked.status_code, 410)
        self.assertEqual(blocked.json()["status"], GuestCheckInSessionStatus.COMPLETED)

    def test_not_open_yet_returns_403(self):
        closed_property = Property.objects.create(
            tenant=self.tenant,
            name="Closed Property",
            slug="closed-property",
            guest_checkin_opens_days_before=30,
        )
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=closed_property,
            booking_code="API-002",
            check_in=date(2026, 12, 1),
            check_out=date(2026, 12, 5),
            adults_count=1,
            booker_name="Future Guest",
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Novi",
            last_name="gost",
            name="Novi gost",
            is_primary=True,
        )
        ensured = GuestCheckInOrchestrator.ensure_session_and_link(
            reservation,
            created_from=GuestCheckInSessionCreatedFrom.EMAIL,
        )
        url = reverse(
            "public-guest-checkin-progress",
            kwargs={"token": str(ensured.session.token)},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "not_open_yet")
        self.assertIn("opens_at", response.json())


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class GuestCheckInWebOcrAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="OCR Tenant", slug="ocr-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="OCR Property",
            slug="ocr-property",
            guest_checkin_opens_days_before=0,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="OCR-001",
            check_in=timezone.localdate(),
            check_out=timezone.localdate() + timedelta(days=2),
            adults_count=1,
            booker_name="OCR Guest",
            amount=Decimal("100.00"),
        )
        self.guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Sophie",
            last_name="Conzelmann",
            name="Sophie Conzelmann",
            is_primary=True,
        )
        ensured = GuestCheckInOrchestrator.ensure_session_and_link(
            self.reservation,
            created_from=GuestCheckInSessionCreatedFrom.EMAIL,
        )
        self.session = ensured.session
        self.token = str(self.session.token)

    @patch("apps.reservations.guest_checkin_web_ocr_service.process_document_intake_job")
    def test_post_documents_creates_web_guest_job(self, mock_process):
        mock_process.return_value = None
        url = reverse(
            "public-guest-checkin-documents",
            kwargs={"token": self.token, "position": 1},
        )
        upload = SimpleUploadedFile("front.jpg", b"fake-image-bytes", content_type="image/jpeg")
        response = self.client.post(url, {"files": upload}, format="multipart")

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("job_id", data)
        job = DocumentIntakeJob.objects.get(pk=data["job_id"])
        self.assertEqual(job.source, DocumentIntakeJobSource.WEB_GUEST)
        self.assertEqual(job.guest_checkin_slot_position, 1)
        self.assertEqual(job.reservation_id, self.reservation.pk)
        mock_process.assert_called_once()

    @patch("apps.reservations.document_intake_service.crop_face_jpeg", return_value=None)
    def test_get_job_poll_applies_to_forced_slot(self, _mock_crop):
        job = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            source=DocumentIntakeJobSource.WEB_GUEST,
            guest_checkin_slot_position=1,
            status=DocumentIntakeJobStatus.DONE,
            ocr_result={
                "persons": [
                    {
                        "given_names": "Sophie",
                        "surnames": "Conzelmann",
                        "document_number": "123456789",
                        "document_type": "national_id",
                        "nationality": "FRA",
                        "date_of_birth": "1988-03-15",
                        "sex": "F",
                        "address": "38 RUE LÉONIE CHAUVEAU, 38300 BOURGOIN-JALLIEU",
                        "front_image_index": 0,
                    }
                ],
            },
            matches=[],
        )
        DocumentIntakeImage.objects.create(
            tenant=self.tenant,
            job=job,
            image=SimpleUploadedFile("front.jpg", b"fake", content_type="image/jpeg"),
            sort_order=0,
        )

        url = reverse(
            "public-guest-checkin-job",
            kwargs={"token": self.token, "job_id": job.pk},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("applied"))
        self.assertEqual(data["slot"]["status"], "ready")
        self.assertEqual(data["slot"]["guest"]["first_name"], "Sophie")
        self.assertNotIn("Novi gost", data["slot"]["guest"]["last_name"])

        self.guest.refresh_from_db()
        self.assertEqual(self.guest.document_number, "123456789")

        job.refresh_from_db()
        self.assertEqual(job.status, DocumentIntakeJobStatus.APPLIED)
        match = job.matches[0]
        self.assertEqual(match["guest_id"], self.guest.pk)
        self.assertEqual(match["candidates"][0]["match_type"], "web_guest_slot")
