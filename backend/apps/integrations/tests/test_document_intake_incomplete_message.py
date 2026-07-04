from datetime import date

from django.test import TestCase

from apps.communications.guest_compose import render_document_intake_incomplete_message
from apps.properties.models import Property
from apps.reservations.document_intake_completeness import DocumentIntakeCompleteness, MissingGuest
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class DocumentIntakeIncompleteMessageTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita", default_language="de")
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

    def test_incomplete_message_mentions_unreadable_photos(self):
        completeness = DocumentIntakeCompleteness(
            is_complete=False,
            missing_guests=[
                MissingGuest(guest_id=1, guest_name="Novi gost (2. odrasli)", adult_ordinal=2),
            ],
            unassigned_image_indices=[2, 3, 4, 5, 6, 7, 8, 9, 10],
            ocr_under_extracted=True,
        )
        body = render_document_intake_incomplete_message(
            self.reservation, completeness, image_count=11,
        )
        self.assertIn("11", body)
        self.assertIn("9", body)
        self.assertIn("Personalausweis", body)
