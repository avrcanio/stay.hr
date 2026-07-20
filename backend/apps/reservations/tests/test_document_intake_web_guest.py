from datetime import date

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.document_intake_context import DocumentIntakeContext
from apps.reservations.document_intake_web_guest import run_web_guest_matching_pipeline
from apps.reservations.models import (
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    Guest,
    Reservation,
)
from apps.tenants.models import Tenant


class DocumentIntakeWebGuestTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="web-guest", name="Web Guest")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Property",
            slug="property",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Sophie Conzelmann",
            adults_count=2,
            check_in=date(2026, 7, 9),
            check_out=date(2026, 7, 10),
            status=Reservation.Status.EXPECTED,
        )
        self.primary = Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Sophie",
            last_name="Conzelmann",
            name="Sophie Conzelmann",
            is_primary=True,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Patrice",
            last_name="Manassero",
            name="Patrice Manassero",
        )

    def test_web_guest_slot_forced_match_targets_slot_guest(self):
        job = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            source=DocumentIntakeJobSource.WEB_GUEST,
            guest_checkin_slot_position=1,
        )
        ctx = DocumentIntakeContext.from_job(job)
        persons = [{"given_names": "UNKNOWN", "surnames": "PERSON"}]
        matches = run_web_guest_matching_pipeline(ctx=ctx, persons=persons)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["guest_id"], self.primary.pk)
        self.assertTrue(matches[0]["auto_apply"])
        self.assertEqual(matches[0]["candidates"][0]["match_type"], "web_guest_slot")
        self.assertNotEqual(matches[0]["guest_name"], "Novi gost")
