from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.properties.models import Property
from apps.reservations.document_intake_audit import audit_document_intake_matches
from apps.reservations.document_intake_match import match_persons_to_guests
from apps.reservations.guest_slots import PLACEHOLDER_FIRST, PLACEHOLDER_LAST
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobStatus, Guest, Reservation
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

    def test_audit_corrects_booker_assigned_to_placeholder(self):
        reservation = self._reservation(booker="Gabriele Böttcher")
        primary = reservation.guests.get(is_primary=True)
        placeholder = reservation.guests.get(is_primary=False)

        persons = [{"given_names": "GABRIELE", "surnames": "BOETTCHER"}]
        matches = match_persons_to_guests(
            tenant_id=self.tenant.pk,
            persons=persons,
            reservation_id=reservation.pk,
        )
        # With digraph fold, match may already hit primary; force wrong slot to test audit.
        matches[0]["guest_id"] = placeholder.pk
        matches[0]["guest_name"] = "Novi gost"
        matches[0]["auto_apply"] = True

        corrected, actions = audit_document_intake_matches(
            reservation=reservation,
            persons=persons,
            matches=matches,
        )

        self.assertTrue(actions)
        self.assertEqual(corrected[0]["guest_id"], primary.pk)

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
        corrected, actions = audit_document_intake_matches(
            reservation=reservation,
            persons=persons,
            matches=matches,
        )

        self.assertEqual(corrected[0]["guest_id"], primary.pk)
        self.assertEqual(corrected[1]["guest_id"], secondary.pk)
        self.assertFalse(actions)

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

        applied = try_apply_complete_job(job, reservation=reservation)
        self.assertEqual(len(applied), 1)
        mock_apply.assert_called_once()
