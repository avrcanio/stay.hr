from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.integrations.channex.review_reply_policy import booking_compliant_fallback
from apps.integrations.channex.review_service import (
    compose_review_reply,
    detect_review_language,
    reply_pending_moderation,
    reply_published,
    review_reply_allowed,
    serialize_channex_review,
)
from apps.integrations.models import ChannexReview, IntegrationConfig
from apps.properties.models import Property
from apps.tenants.models import Tenant


class ChannexReviewReplyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(tenant=self.tenant, name="Uzorita", slug="uzorita")
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )

    def _review(self, **kwargs) -> ChannexReview:
        defaults = {
            "tenant": self.tenant,
            "integration": self.integration,
            "channex_review_id": "review-test-1",
            "ota": "BookingCom",
            "overall_score": Decimal("6.0"),
            "received_at": timezone.now(),
            "expired_at": timezone.now() + timedelta(days=90),
        }
        defaults.update(kwargs)
        return ChannexReview.objects.create(**defaults)

    def test_detect_slovak_review_language(self):
        content = "izba veľka priestranna, záchod bol špinavy"
        self.assertEqual(detect_review_language(content), "sk")

    def test_review_reply_allowed_when_reply_submitted_not_published(self):
        row = self._review(
            reply="Draft reply waiting for Booking moderation",
            is_replied=True,
            reply_sent_at=None,
        )
        self.assertTrue(review_reply_allowed(row))

    def test_review_reply_not_allowed_when_published(self):
        row = self._review(
            reply="Published reply",
            is_replied=True,
            reply_sent_at=timezone.now(),
        )
        self.assertFalse(review_reply_allowed(row))

    def test_reply_pending_moderation_bookingcom(self):
        row = self._review(reply="Waiting", is_replied=True, reply_sent_at=None)
        self.assertTrue(reply_pending_moderation(row))
        self.assertFalse(reply_published(row))

    def test_serialize_includes_moderation_fields(self):
        row = self._review(
            content="izba veľka",
            reply="Odpoveď",
            is_replied=True,
            reply_sent_at=None,
        )
        data = serialize_channex_review(row)
        self.assertEqual(data["suggested_reply_language"], "sk")
        self.assertTrue(data["reply_pending_moderation"])
        self.assertFalse(data["reply_published"])
        self.assertTrue(data["can_reply"])


class ChannexReviewComposePolicyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )

    def _review(self, **kwargs) -> ChannexReview:
        defaults = {
            "tenant": self.tenant,
            "integration": self.integration,
            "channex_review_id": "review-compose-policy",
            "ota": "BookingCom",
            "content": "The bathroom was dirty.",
            "guest_name": "Jane Doe",
            "overall_score": Decimal("4.0"),
            "received_at": timezone.now(),
            "expired_at": timezone.now() + timedelta(days=90),
        }
        defaults.update(kwargs)
        return ChannexReview.objects.create(**defaults)

    @patch("apps.integrations.channex.review_service.complete_chat")
    @patch("apps.integrations.channex.review_service.llm_configured", return_value=True)
    def test_compose_uses_fallback_when_llm_non_compliant(self, _mock_llm, mock_chat):
        mock_chat.return_value = "Jane, we apologize the bathroom was dirty. Call us at +385991234567."
        row = self._review()
        body, llm_used, lang = compose_review_reply(row)
        self.assertTrue(llm_used)
        self.assertEqual(body, booking_compliant_fallback(lang))
        self.assertNotIn("Jane", body)
