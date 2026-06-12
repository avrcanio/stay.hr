from datetime import date

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.document_intake_completeness import evaluate_completeness
from apps.reservations.models import Guest, Reservation
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
