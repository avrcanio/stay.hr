from django.test import TestCase

from apps.integrations.channex.review_reply_policy import (
    booking_compliant_fallback,
    validate_review_reply,
)
from apps.integrations.channex.review_service import BOOKING_COM_OTA


class ReviewReplyPolicyTests(TestCase):
    def test_fallback_templates_pass_validation(self):
        for lang in ("hr", "en", "de", "sk", "es", "fr"):
            text = booking_compliant_fallback(lang)
            errors = validate_review_reply(text, ota=BOOKING_COM_OTA)
            self.assertEqual(errors, [], msg=f"lang={lang}")

    def test_rejects_guest_name(self):
        errors = validate_review_reply(
            "Thank you Pierre for your feedback.",
            ota=BOOKING_COM_OTA,
            guest_name="Pierre",
        )
        self.assertTrue(errors)

    def test_rejects_url(self):
        errors = validate_review_reply(
            "Please visit https://example.com for details.",
            ota=BOOKING_COM_OTA,
        )
        self.assertTrue(errors)

    def test_rejects_booking_code(self):
        errors = validate_review_reply(
            "Thank you regarding booking 5238895494.",
            ota=BOOKING_COM_OTA,
        )
        self.assertTrue(errors)

    def test_rejects_repeated_negative_review_word(self):
        errors = validate_review_reply(
            "We are sorry the bathroom was dirty.",
            ota=BOOKING_COM_OTA,
            review_content="The bathroom was dirty and unacceptable.",
        )
        self.assertTrue(errors)

    def test_accepts_neutral_reply(self):
        errors = validate_review_reply(
            booking_compliant_fallback("en"),
            ota=BOOKING_COM_OTA,
            guest_name="Guest Test",
            review_content="The bathroom was dirty.",
        )
        self.assertEqual(errors, [])
