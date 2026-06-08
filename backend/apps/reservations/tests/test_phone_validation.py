from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.reservations.phone_validation import normalize_booker_phone, validate_booker_phone


class BookerPhoneValidationTests(SimpleTestCase):
    def test_normalize_fixes_plus_minus_typo(self):
        self.assertEqual(normalize_booker_phone("±385977402538"), "+385977402538")

    def test_normalize_strips_spaces_and_invalid_chars(self):
        self.assertEqual(normalize_booker_phone("+385 97 740 2538"), "+385977402538")

    def test_validate_accepts_international_format(self):
        self.assertEqual(validate_booker_phone("+385977402538"), "+385977402538")

    def test_validate_rejects_missing_plus(self):
        with self.assertRaises(ValidationError):
            validate_booker_phone("385977402538")

    def test_validate_normalizes_plus_minus_typo(self):
        self.assertEqual(validate_booker_phone("±385977402538"), "+385977402538")

    def test_validate_allows_empty(self):
        self.assertEqual(validate_booker_phone(""), "")
