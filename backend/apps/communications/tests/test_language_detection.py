from django.test import TestCase

from apps.communications.language_detection import detect


class LanguageDetectionTests(TestCase):
    def test_italian_message(self):
        result = detect("Grazie, possiamo arrivare in sera?")
        self.assertEqual(result.language, "it")
        self.assertGreaterEqual(result.confidence, 0.65)

    def test_german_message(self):
        result = detect("Können wir spaeter ankommen?")
        self.assertEqual(result.language, "de")
        self.assertGreaterEqual(result.confidence, 0.65)

    def test_croatian_message(self):
        result = detect("Možemo li doći kasnije večeras?")
        self.assertEqual(result.language, "hr")
        self.assertGreaterEqual(result.confidence, 0.65)

    def test_english_default(self):
        result = detect("See you tomorrow")
        self.assertEqual(result.language, "en")
        self.assertLess(result.confidence, 0.65)

    def test_unknown_empty(self):
        result = detect("")
        self.assertEqual(result.language, "unknown")
        self.assertEqual(result.confidence, 0.0)

    def test_unknown_emoji_only(self):
        result = detect("👍")
        self.assertEqual(result.language, "unknown")
        self.assertEqual(result.confidence, 0.0)

    def test_polish_message(self):
        result = detect("Dziękuję, czy możemy przyjechać później?")
        self.assertEqual(result.language, "pl")
