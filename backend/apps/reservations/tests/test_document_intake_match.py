from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.properties.models import Property
from apps.reservations.document_intake_match import match_persons_to_guests
from apps.reservations.guest_slots import PLACEHOLDER_FIRST, PLACEHOLDER_LAST
from apps.reservations.models import Guest, Reservation


class DocumentIntakeMatchTests(TestCase):
    def setUp(self):
        from apps.tenants.models import Tenant

        self.tenant = Tenant.objects.create(name="Match Test", slug="match-test")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Test Property",
            slug="test-prop",
            address="Test",
        )

    def _reservation(self, *, pk_suffix: int, booker: str, check_in: date) -> Reservation:
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id=f"ext-{pk_suffix}",
            booking_code=f"code-{pk_suffix}",
            check_in=check_in,
            check_out=check_in + timedelta(days=1),
            status=Reservation.Status.EXPECTED,
            booker_name=booker,
            adults_count=2,
            persons_count=2,
        )
        parts = booker.split()
        first = parts[0] if parts else booker
        last = parts[-1] if len(parts) > 1 else ""
        Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name=first,
            last_name=last,
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

    def test_middle_name_on_document_matches_booker(self):
        today = timezone.now().date()
        target = self._reservation(pk_suffix=837, booker="Daniela Heczko", check_in=today)
        self._reservation(pk_suffix=70, booker="Other Guest", check_in=today)

        persons = [
            {
                "given_names": "DANIELA HELENA",
                "surnames": "HECZKO",
            },
            {
                "given_names": "ŁUKASZ PIOTR",
                "surnames": "KURAŚ",
            },
        ]
        matches = match_persons_to_guests(tenant_id=self.tenant.pk, persons=persons)

        self.assertEqual(len(matches), 2)
        daniela = matches[0]
        self.assertTrue(daniela["auto_apply"])
        self.assertEqual(daniela["reservation_id"], target.pk)
        self.assertEqual(daniela["confidence"], "high")

        companion = matches[1]
        self.assertTrue(companion["auto_apply"])
        self.assertEqual(companion["reservation_id"], target.pk)
        self.assertNotEqual(companion["guest_id"], daniela["guest_id"])

    def test_comma_given_names_match_booker_with_accent(self):
        """OCR comma-separated given names + surname (François Hartweg scenario)."""
        today = timezone.now().date()
        target = self._reservation(pk_suffix=8, booker="François Hartweg", check_in=today)
        self._reservation(pk_suffix=70, booker="Other Guest", check_in=today)

        persons = [
            {
                "given_names": "Francois, Jacques, Alfred",
                "surnames": "HARTWEG",
            },
            {
                "given_names": "Anne, Elisabeth OECHEL ep. HARTWEG",
                "surnames": "",
            },
        ]
        matches = match_persons_to_guests(tenant_id=self.tenant.pk, persons=persons)

        self.assertEqual(len(matches), 2)
        francois = matches[0]
        self.assertTrue(francois["auto_apply"])
        self.assertEqual(francois["reservation_id"], target.pk)
        self.assertEqual(francois["confidence"], "high")

        spouse = matches[1]
        self.assertTrue(spouse["auto_apply"])
        self.assertEqual(spouse["reservation_id"], target.pk)
        self.assertNotEqual(spouse["guest_id"], francois["guest_id"])
