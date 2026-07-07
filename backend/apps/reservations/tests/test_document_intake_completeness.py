from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.document_intake_audit import run_document_intake_matching_pipeline
from apps.reservations.document_intake_completeness import evaluate_completeness
from apps.reservations.models import Guest, IdDocument, Reservation
from apps.reservations.tests.fixtures.document_intake.load_fixture import (
    build_reservation_from_fixture,
)
from apps.tenants.models import Tenant


class _FakeImage:
    def __init__(self, sort_order: int, detected_side: str = ""):
        self.sort_order = sort_order
        self.detected_side = detected_side


class DocumentIntakeCompletenessTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita", default_language="hr")
        self.property = Property.objects.create(tenant=self.tenant, name="Uzorita", slug="uzorita")
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Jannik Enders",
            booker_phone="+49123456789",
            adults_count=2,
            check_in=date(2026, 6, 11),
            check_out=date(2026, 6, 13),
            status=Reservation.Status.EXPECTED,
        )
        self.primary = Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Jannik",
            last_name="Enders",
            name="Jannik Enders",
            is_primary=True,
        )

    def _evaluate(self, persons, matches, images=None):
        if images is None:
            images = [_FakeImage(i) for i in range(8)]
        return evaluate_completeness(
            reservation=self.reservation,
            persons=persons,
            matches=matches,
            images=images,
        )

    def test_two_adults_with_front_back_complete(self):
        persons = [
            {
                "given_names": "Jannik",
                "surnames": "Enders",
                "document_type": "national_id",
                "front_image_index": 0,
                "back_image_index": 1,
            },
            {
                "given_names": "Anna",
                "surnames": "Voigt",
                "document_type": "national_id",
                "front_image_index": 2,
                "back_image_index": 3,
            },
        ]
        matches = [
            {
                "person_index": 0,
                "auto_apply": True,
                "guest_id": self.primary.pk,
                "reservation_id": self.reservation.pk,
                "guest_name": "Jannik Enders",
            },
            {
                "person_index": 1,
                "auto_apply": True,
                "guest_id": 999,
                "reservation_id": self.reservation.pk,
                "guest_name": "Anna Voigt",
            },
        ]
        second = Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Anna",
            last_name="Voigt",
            name="Anna Voigt",
        )
        matches[1]["guest_id"] = second.pk

        result = self._evaluate(persons, matches)
        self.assertTrue(result.is_complete)
        self.assertEqual(result.missing_guests, [])
        self.assertEqual(result.missing_sides, [])
        self.assertEqual(result.unmatched_persons, [])

    def test_one_person_missing_second_adult(self):
        persons = [
            {
                "given_names": "Jannik",
                "surnames": "Enders",
                "document_type": "national_id",
                "front_image_index": 0,
                "back_image_index": 1,
            },
        ]
        matches = [
            {
                "person_index": 0,
                "auto_apply": True,
                "guest_id": self.primary.pk,
                "reservation_id": self.reservation.pk,
                "guest_name": "Jannik Enders",
            },
        ]
        result = self._evaluate(persons, matches)
        self.assertFalse(result.is_complete)
        self.assertEqual(len(result.missing_guests), 1)
        self.assertIn("odrasli", result.missing_guests[0].guest_name)

    def test_missing_back_side(self):
        persons = [
            {
                "given_names": "Jannik",
                "surnames": "Enders",
                "document_type": "national_id",
                "front_image_index": 0,
            },
        ]
        matches = [
            {
                "person_index": 0,
                "auto_apply": True,
                "guest_id": self.primary.pk,
                "reservation_id": self.reservation.pk,
                "guest_name": "Jannik Enders",
            },
        ]
        result = self._evaluate(persons, matches)
        self.assertFalse(result.is_complete)
        self.assertEqual(len(result.missing_sides), 1)
        self.assertEqual(result.missing_sides[0].side, "back")

    def test_passport_back_index_only_is_complete(self):
        self.reservation.adults_count = 1
        self.reservation.save(update_fields=["adults_count"])
        persons = [
            {
                "given_names": "MILE",
                "surnames": "SUJIC",
                "document_type": "passport",
                "front_image_index": None,
                "back_image_index": 0,
            },
        ]
        matches = [
            {
                "person_index": 0,
                "auto_apply": True,
                "guest_id": self.primary.pk,
                "reservation_id": self.reservation.pk,
                "guest_name": "MILE SUJIC",
            },
        ]
        result = self._evaluate(persons, matches, images=[_FakeImage(0)])
        self.assertTrue(result.is_complete)
        self.assertEqual(result.missing_sides, [])

    def test_stored_front_plus_batch_back_is_complete(self):
        """Incremental capture: front already on guest, this batch only has back."""
        self.reservation.adults_count = 1
        self.reservation.save(update_fields=["adults_count"])
        IdDocument.objects.create(
            guest=self.primary,
            front_photo=SimpleUploadedFile("front.jpg", b"fake-front", content_type="image/jpeg"),
        )
        persons = [
            {
                "given_names": "Jannik",
                "surnames": "Enders",
                "document_type": "national_id",
                "back_image_index": 0,
            },
        ]
        matches = [
            {
                "person_index": 0,
                "auto_apply": True,
                "guest_id": self.primary.pk,
                "reservation_id": self.reservation.pk,
                "guest_name": "Jannik Enders",
            },
        ]
        result = self._evaluate(
            persons,
            matches,
            images=[_FakeImage(0, detected_side="back")],
        )
        self.assertTrue(result.is_complete)
        self.assertEqual(result.missing_sides, [])

    def test_unassigned_image_indices(self):
        persons = [
            {
                "given_names": "Gabriele",
                "surnames": "Boettcher",
                "document_type": "national_id",
                "front_image_index": 0,
                "back_image_index": 1,
            },
        ]
        matches = [
            {
                "person_index": 0,
                "auto_apply": True,
                "guest_id": self.primary.pk,
                "reservation_id": self.reservation.pk,
                "guest_name": "Gabriele Boettcher",
            },
        ]
        images = [_FakeImage(i) for i in range(11)]
        result = self._evaluate(persons, matches, images=images)
        self.assertEqual(result.unassigned_image_indices, list(range(2, 11)))
        self.assertTrue(result.ocr_under_extracted)
        self.assertFalse(result.is_complete)

    def test_ocr_under_extracted_one_person_two_adults(self):
        persons = [
            {
                "given_names": "Jannik",
                "surnames": "Enders",
                "document_type": "national_id",
                "front_image_index": 0,
                "back_image_index": 1,
            },
        ]
        matches = [
            {
                "person_index": 0,
                "auto_apply": True,
                "guest_id": self.primary.pk,
                "reservation_id": self.reservation.pk,
                "guest_name": "Jannik Enders",
            },
        ]
        result = self._evaluate(persons, matches, images=[_FakeImage(0), _FakeImage(1)])
        self.assertTrue(result.ocr_under_extracted)
        self.assertEqual(result.unassigned_image_indices, [])


class DocumentIntakeCompletenessPolicyRegressionTests(TestCase):
    """Regression: completeness delegates missing_guests to document_expectations."""

    def setUp(self):
        self.tenant = Tenant.objects.create(slug="completeness-policy", name="Policy")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita-completeness-policy",
        )

    def test_978_missing_guests_capped_at_adults_count(self):
        reservation, _guests, ocr_data, _meta = build_reservation_from_fixture(
            tenant=self.tenant,
            property=self.property,
            scenario="978",
        )
        images = [_FakeImage(i) for i in range(len(ocr_data.get("images") or ocr_data["persons"]))]
        result = evaluate_completeness(
            reservation=reservation,
            persons=ocr_data["persons"],
            matches=[],
            images=images,
        )
        self.assertEqual(len(result.missing_guests), 4)
        self.assertFalse(result.is_complete)

    def test_978_complete_when_all_adult_slots_matched(self):
        reservation, _guests, ocr_data, _meta = build_reservation_from_fixture(
            tenant=self.tenant,
            property=self.property,
            scenario="978",
        )
        persons = ocr_data["persons"]
        matches = run_document_intake_matching_pipeline(
            tenant_id=self.tenant.pk,
            reservation=reservation,
            persons=persons,
        )
        images = [_FakeImage(i) for i in range(len(ocr_data.get("images") or persons))]
        result = evaluate_completeness(
            reservation=reservation,
            persons=persons,
            matches=matches,
            images=images,
        )
        self.assertEqual(result.missing_guests, [])
        self.assertTrue(result.is_complete)

    def test_horvat_missing_guests_count_is_adults_not_persons(self):
        reservation, _guests, ocr_data, _meta = build_reservation_from_fixture(
            tenant=self.tenant,
            property=self.property,
            scenario="horvat",
        )
        images = [_FakeImage(i) for i in range(len(ocr_data.get("images") or ocr_data["persons"]))]
        result = evaluate_completeness(
            reservation=reservation,
            persons=ocr_data["persons"],
            matches=[],
            images=images,
        )
        self.assertEqual(len(result.missing_guests), 2)
        self.assertFalse(result.is_complete)
