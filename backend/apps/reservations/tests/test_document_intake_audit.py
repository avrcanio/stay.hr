from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.properties.models import Property
from apps.reservations.document_intake_audit import (
    MATCHER_FIELDS,
    VALIDATOR_FIELDS,
    assert_audit_only_touched_validator_fields,
    audit_document_intake_matches,
)
from apps.reservations.document_intake_match import (
    enforce_unique_guest_assignments,
    match_persons_to_guests,
)
from apps.reservations.guest_slots import PLACEHOLDER_FIRST, PLACEHOLDER_LAST
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobStatus, Guest, Reservation
from apps.reservations.tests.fixtures.document_intake.load_fixture import build_reservation_from_fixture
from apps.tenants.models import Tenant


class DocumentIntakeAuditTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Audit Test", slug="audit-test")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Test Property",
            slug="audit-prop",
            address="Test",
        )

    def _reservation(self, *, booker: str) -> Reservation:
        today = timezone.now().date()
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="ext-audit",
            booking_code="code-audit",
            check_in=today,
            check_out=today + timedelta(days=2),
            status=Reservation.Status.EXPECTED,
            booker_name=booker,
            adults_count=2,
            persons_count=2,
        )
        parts = booker.split()
        Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name=parts[0],
            last_name=parts[-1] if len(parts) > 1 else "",
            name=booker,
            is_primary=True,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name=PLACEHOLDER_FIRST,
            last_name=PLACEHOLDER_LAST,
            name="Novi gost",
            is_primary=False,
        )
        return reservation

    def test_matcher_maps_booker_to_primary_without_audit_reassignment(self):
        reservation = self._reservation(booker="Gabriele Böttcher")
        primary = reservation.guests.get(is_primary=True)

        persons = [{"given_names": "GABRIELE", "surnames": "BOETTCHER"}]
        matches = match_persons_to_guests(
            tenant_id=self.tenant.pk,
            persons=persons,
            reservation_id=reservation.pk,
        )
        matches = enforce_unique_guest_assignments(matches)
        corrected, actions = audit_document_intake_matches(
            reservation=reservation,
            persons=persons,
            matches=matches,
        )

        self.assertEqual(corrected[0]["guest_id"], primary.pk)
        self.assertFalse(actions)

    def test_companion_still_maps_to_secondary(self):
        reservation = self._reservation(booker="Hans Fischer")
        primary = reservation.guests.get(is_primary=True)
        secondary = reservation.guests.get(is_primary=False)

        persons = [
            {"given_names": "HANS", "surnames": "FISCHER"},
            {"given_names": "ELKE", "surnames": "FISCHER"},
        ]
        matches = match_persons_to_guests(
            tenant_id=self.tenant.pk,
            persons=persons,
            reservation_id=reservation.pk,
        )
        matches = enforce_unique_guest_assignments(matches)
        corrected, actions = audit_document_intake_matches(
            reservation=reservation,
            persons=persons,
            matches=matches,
        )

        self.assertEqual(corrected[0]["guest_id"], primary.pk)
        self.assertEqual(corrected[1]["guest_id"], secondary.pk)
        self.assertFalse(actions)

    def test_audit_rejects_booker_first_name_mismatch_on_primary(self):
        reservation = self._reservation(booker="Laura Lysak")
        primary = reservation.guests.get(is_primary=True)
        placeholder = reservation.guests.get(is_primary=False)

        persons = [{"given_names": "DAINIUS", "surnames": "LYSAK"}]
        matches = [
            {
                "person_index": 0,
                "person_name": "DAINIUS LYSAK",
                "auto_apply": True,
                "guest_id": primary.pk,
                "guest_name": primary.name,
                "reservation_id": reservation.pk,
                "confidence": "high",
                "candidates": [],
            }
        ]
        corrected, actions = audit_document_intake_matches(
            reservation=reservation,
            persons=persons,
            matches=matches,
        )

        self.assertEqual(corrected[0]["guest_id"], primary.pk)
        self.assertFalse(corrected[0]["auto_apply"])
        self.assertEqual(corrected[0]["reject_reason"], "booker_first_name_mismatch")
        self.assertTrue(actions)
        self.assertNotEqual(corrected[0]["guest_id"], placeholder.pk)

    def _assert_audit_never_mutates_matcher_fields(self, *, reservation, persons, matches):
        matches_before = deepcopy(matches)
        audit_document_intake_matches(
            reservation=reservation,
            persons=persons,
            matches=matches,
        )
        for before, after in zip(matches_before, matches):
            for field in MATCHER_FIELDS:
                self.assertEqual(before.get(field), after.get(field), field)
            assert_audit_only_touched_validator_fields(before, after)

    def test_audit_never_mutates_matcher_fields_booker_scenario(self):
        reservation = self._reservation(booker="Gabriele Böttcher")
        persons = [{"given_names": "GABRIELE", "surnames": "BOETTCHER"}]
        matches = match_persons_to_guests(
            tenant_id=self.tenant.pk,
            persons=persons,
            reservation_id=reservation.pk,
        )
        self._assert_audit_never_mutates_matcher_fields(
            reservation=reservation,
            persons=persons,
            matches=matches,
        )

    def test_audit_never_mutates_matcher_fields_companion_scenario(self):
        reservation = self._reservation(booker="Hans Fischer")
        persons = [
            {"given_names": "HANS", "surnames": "FISCHER"},
            {"given_names": "ELKE", "surnames": "FISCHER"},
        ]
        matches = match_persons_to_guests(
            tenant_id=self.tenant.pk,
            persons=persons,
            reservation_id=reservation.pk,
        )
        self._assert_audit_never_mutates_matcher_fields(
            reservation=reservation,
            persons=persons,
            matches=matches,
        )

    def test_audit_never_mutates_matcher_fields_978_fixture(self):
        reservation, _guests, ocr_data, _meta = build_reservation_from_fixture(
            tenant=self.tenant,
            property=self.property,
            scenario="978",
        )
        persons = ocr_data["persons"]
        matches = match_persons_to_guests(
            tenant_id=self.tenant.pk,
            persons=persons,
            reservation_id=reservation.pk,
        )
        matches = enforce_unique_guest_assignments(matches)
        self._assert_audit_never_mutates_matcher_fields(
            reservation=reservation,
            persons=persons,
            matches=matches,
        )

    def test_validator_fields_documented(self):
        self.assertIn("auto_apply", VALIDATOR_FIELDS)
        self.assertIn("audit_status", VALIDATOR_FIELDS)
        self.assertIn("reject_reason", VALIDATOR_FIELDS)

    @patch("apps.reservations.document_intake_service.apply_document_intake_job")
    def test_try_apply_complete_job_when_ready(self, mock_apply):
        reservation = self._reservation(booker="Gabriele Böttcher")
        reservation.adults_count = 1
        reservation.persons_count = 1
        reservation.save(update_fields=["adults_count", "persons_count"])
        reservation.guests.filter(is_primary=False).delete()
        primary = reservation.guests.get(is_primary=True)
        job = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            status=DocumentIntakeJobStatus.DONE,
            ocr_result={
                "persons": [
                    {
                        "given_names": "GABRIELE",
                        "surnames": "BOETTCHER",
                        "document_number": "X1",
                        "document_type": "passport",
                        "front_image_index": 0,
                    }
                ],
                "images": [{"index": 0, "side": "front"}],
            },
            matches=[
                {
                    "person_index": 0,
                    "auto_apply": True,
                    "guest_id": primary.pk,
                    "reservation_id": reservation.pk,
                }
            ],
        )
        from apps.reservations.models import DocumentIntakeImage
        from django.core.files.base import ContentFile

        DocumentIntakeImage.objects.create(
            tenant=self.tenant,
            job=job,
            image=ContentFile(b"fake", name="front.jpg"),
            sort_order=0,
            detected_side="front",
        )
        mock_apply.return_value = [{"guest_id": primary.pk}]

        from apps.reservations.document_intake_audit import try_apply_complete_job
        from apps.reservations.document_intake_context import DocumentIntakeContext

        applied = try_apply_complete_job(DocumentIntakeContext.from_job(job))
        self.assertEqual(len(applied), 1)
        mock_apply.assert_called_once()
