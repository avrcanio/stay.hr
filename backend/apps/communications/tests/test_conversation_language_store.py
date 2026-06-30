from django.test import TestCase
from django.utils import timezone

from apps.communications.conversation_language_store import load, maybe_update
from apps.communications.guest_language_context import LanguageSource
from apps.communications.language_detection import DetectionResult
from apps.communications.models import GuestMessageThreadState
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class ConversationLanguageStoreTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita B&B",
            slug="uzorita",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="123",
            check_in="2026-06-05",
            check_out="2026-06-09",
            status=Reservation.Status.EXPECTED,
            booker_name="Test Guest",
        )

    def test_update_above_threshold(self):
        candidate = DetectionResult(language="it", confidence=0.85)
        updated = maybe_update(
            self.reservation,
            candidate,
            channel="whatsapp",
            received_at=timezone.now(),
        )
        self.assertTrue(updated)
        stored = load(self.reservation)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.language, "it")
        self.assertEqual(stored.source, LanguageSource.MESSAGE)

    def test_thumbs_up_does_not_change_existing(self):
        state = GuestMessageThreadState.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            conversation_language="it",
            conversation_language_source=LanguageSource.MESSAGE.value,
        )
        updated = maybe_update(
            self.reservation,
            DetectionResult(language="en", confidence=0.35),
            channel="whatsapp",
        )
        self.assertFalse(updated)
        state.refresh_from_db()
        self.assertEqual(state.conversation_language, "it")

    def test_ok_does_not_update(self):
        updated = maybe_update(
            self.reservation,
            DetectionResult(language="en", confidence=0.35),
            channel="whatsapp",
        )
        self.assertFalse(updated)
        self.assertIsNone(load(self.reservation))

    def test_low_confidence_skipped(self):
        updated = maybe_update(
            self.reservation,
            DetectionResult(language="en", confidence=0.35),
            channel="email",
        )
        self.assertFalse(updated)
