from django.test import TestCase
from django.utils import timezone

from apps.communications.guest_language_context import LanguageMode, LanguageSource
from apps.communications.guest_language_resolver import GuestLanguageResolver
from apps.communications.models import GuestInboundMessage, GuestMessageChannel, GuestMessageThreadState
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class GuestLanguageResolverTests(TestCase):
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
            booker_country="DE",
        )

    def test_german_guest_writes_english(self):
        ctx = GuestLanguageResolver.resolve(
            self.reservation,
            mode=LanguageMode.REACTIVE,
            message_text="We will arrive around 8pm tonight, thanks",
        )
        self.assertEqual(ctx.language, "en")
        self.assertEqual(ctx.source, LanguageSource.MESSAGE)

    def test_proactive_it_country(self):
        self.reservation.booker_country = "IT"
        self.reservation.save(update_fields=["booker_country"])
        ctx = GuestLanguageResolver.resolve(
            self.reservation,
            mode=LanguageMode.PROACTIVE,
        )
        self.assertEqual(ctx.language, "it")
        self.assertEqual(ctx.source, LanguageSource.COUNTRY)

    def test_conversation_persists_through_emoji_reply(self):
        GuestMessageThreadState.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            conversation_language="it",
            conversation_language_source=LanguageSource.MESSAGE.value,
        )
        GuestInboundMessage.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            channel=GuestMessageChannel.WHATSAPP,
            body_text="👍",
            received_at=timezone.now(),
        )
        ctx = GuestLanguageResolver.resolve(
            self.reservation,
            mode=LanguageMode.REACTIVE,
        )
        self.assertEqual(ctx.language, "it")
        self.assertEqual(ctx.source, LanguageSource.CONVERSATION)

    def test_italian_message_detected(self):
        ctx = GuestLanguageResolver.resolve(
            self.reservation,
            mode=LanguageMode.REACTIVE,
            message_text="Grazie, possiamo arrivare stasera?",
        )
        self.assertEqual(ctx.language, "it")
        self.assertEqual(ctx.source, LanguageSource.MESSAGE)
