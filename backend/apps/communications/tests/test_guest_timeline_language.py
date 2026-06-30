from django.test import TestCase

from apps.communications.guest_timeline_language import (
    find_detectable_inbound_text,
    is_detectable_inbound_text,
)


class GuestTimelineLanguageTests(TestCase):
    def test_detectable_long_enough(self):
        self.assertTrue(is_detectable_inbound_text("We will arrive at 8pm"))

    def test_not_detectable_ok(self):
        self.assertFalse(is_detectable_inbound_text("ok"))

    def test_not_detectable_thumbs_up(self):
        self.assertFalse(is_detectable_inbound_text("👍"))

    def test_three_words_counts(self):
        self.assertTrue(is_detectable_inbound_text("see you soon"))
