from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.document_intake_audit import run_document_intake_matching_pipeline
from apps.reservations.document_intake_context import DocumentIntakeContext
from apps.reservations.document_intake_service import apply_document_intake_job
from apps.reservations.models import (
    DocumentIntakeImage,
    DocumentIntakeJob,
    DocumentIntakeJobStatus,
    Guest,
    Reservation,
)
from apps.reservations.tests.fixtures.document_intake.load_fixture import (
    build_reservation_from_fixture,
    load_document_intake_fixture,
)
from apps.tenants.models import Tenant


class DocumentIntakeGolden978Tests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita-golden")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita-golden",
            address="Test",
        )

    def _build_978(self):
        return build_reservation_from_fixture(
            tenant=self.tenant,
            property=self.property,
            scenario="978",
        )

    def test_978_match_phase_unique_guest_assignments(self):
        reservation, _guests, ocr_data, _meta = self._build_978()
        persons = ocr_data["persons"]
        matches = run_document_intake_matching_pipeline(
            tenant_id=self.tenant.pk,
            reservation=reservation,
            persons=persons,
        )

        self.assertEqual(len(matches), 4)
        self.assertNotEqual(matches[0]["guest_id"], matches[1]["guest_id"])

        auto_guest_ids = {m["guest_id"] for m in matches if m.get("auto_apply")}
        self.assertEqual(len(auto_guest_ids), 4)

        laura_guest = reservation.guests.get(is_primary=True)
        dainius_match = matches[0]
        laura_match = matches[1]
        self.assertEqual(laura_match["guest_id"], laura_guest.pk)
        self.assertNotEqual(dainius_match["guest_id"], laura_guest.pk)

    @patch("apps.reservations.document_intake_service.crop_face_jpeg", return_value=None)
    def test_978_apply_phase_populates_guest_fields(self, _mock_crop):
        reservation, _guests, ocr_data, _meta = self._build_978()
        persons = ocr_data["persons"]
        matches = run_document_intake_matching_pipeline(
            tenant_id=self.tenant.pk,
            reservation=reservation,
            persons=persons,
        )
        job = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            status=DocumentIntakeJobStatus.DONE,
            ocr_result={"persons": persons, "images": ocr_data.get("images") or []},
            matches=matches,
        )
        for idx in range(4):
            DocumentIntakeImage.objects.create(
                tenant=self.tenant,
                job=job,
                image=SimpleUploadedFile(f"p{idx}.jpg", b"fake", content_type="image/jpeg"),
                sort_order=idx,
                detected_side="passport",
            )

        apply_document_intake_job(
            DocumentIntakeContext.from_job(job),
            whatsapp_reply=False,
            allow_partial=True,
        )

        dainius = Guest.objects.get(reservation=reservation, document_number="25246986")
        self.assertEqual(dainius.first_name, "DAINIUS")
        self.assertEqual(dainius.last_name, "LYSAK")
        self.assertEqual(dainius.date_of_birth, date(1982, 4, 24))

        laura = Guest.objects.get(reservation=reservation, document_number="25246987")
        self.assertEqual(laura.first_name, "LAURA")
        self.assertEqual(laura.last_name, "LYSAK")
        self.assertEqual(laura.date_of_birth, date(1984, 6, 15))

        odeta = Guest.objects.get(reservation=reservation, document_number="25246988")
        self.assertEqual(odeta.first_name, "ODETA")
        self.assertEqual(odeta.last_name, "BELAZARE")
        self.assertEqual(odeta.date_of_birth, date(1986, 3, 10))

        rimas = Guest.objects.get(reservation=reservation, document_number="25246989")
        self.assertEqual(rimas.first_name, "RIMAS")
        self.assertEqual(rimas.last_name, "BELAZARAS")
        self.assertEqual(rimas.date_of_birth, date(1985, 8, 22))

    def test_horvat_match_phase_booker_and_companions(self):
        reservation, guests, ocr_data, _meta = build_reservation_from_fixture(
            tenant=self.tenant,
            property=self.property,
            scenario="horvat",
        )
        persons = ocr_data["persons"]
        matches = run_document_intake_matching_pipeline(
            tenant_id=self.tenant.pk,
            reservation=reservation,
            persons=persons,
        )

        primary = reservation.guests.get(is_primary=True)
        secondary = next(g for g in guests if not g.is_primary and g.first_name == "Novi")
        marko = reservation.guests.get(first_name="Marko")

        self.assertEqual(matches[0]["guest_id"], primary.pk)
        self.assertEqual(matches[1]["guest_id"], secondary.pk)
        self.assertEqual(matches[2]["guest_id"], marko.pk)
        self.assertEqual(len({m["guest_id"] for m in matches if m.get("auto_apply")}), 3)

    def test_fixture_loader_returns_expected_shape(self):
        fixture = load_document_intake_fixture("978")
        self.assertIn("reservation", fixture)
        self.assertIn("ocr", fixture)
        self.assertEqual(len(fixture["ocr"]["persons"]), 4)
        self.assertEqual(fixture["reservation"]["booker_name"], "Laura Lysak")
