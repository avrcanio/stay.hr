from django.test import SimpleTestCase

from apps.reservations.reports.recipients import parse_financial_report_recipients


class ParseFinancialReportRecipientsTests(SimpleTestCase):
    def test_empty(self):
        self.assertEqual(parse_financial_report_recipients(""), [])
        self.assertEqual(parse_financial_report_recipients("   "), [])

    def test_comma_and_semicolon_separated(self):
        self.assertEqual(
            parse_financial_report_recipients("a@example.com, b@example.com; c@example.com"),
            ["a@example.com", "b@example.com", "c@example.com"],
        )

    def test_deduplicates_case_insensitive(self):
        self.assertEqual(
            parse_financial_report_recipients("A@Example.com, a@example.com"),
            ["A@Example.com"],
        )

    def test_skips_invalid_addresses(self):
        self.assertEqual(
            parse_financial_report_recipients("valid@example.com, not-an-email, also@example.com"),
            ["valid@example.com", "also@example.com"],
        )
