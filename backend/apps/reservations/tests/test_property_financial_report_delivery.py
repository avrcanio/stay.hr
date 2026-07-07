from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.properties.models import Property
from apps.reservations.reports.delivery import (
    deliver_property_financial_report_email,
    previous_calendar_month_check_out_period,
)
from apps.reservations.reports.types import PropertyFinancialReportParams
from apps.reservations.tests.fixtures.property_financial_report_result import (
    sample_property_financial_report_result,
)
from apps.tenants.models import Tenant


class PreviousCalendarMonthPeriodTests(SimpleTestCase):
    def test_july_reference_returns_june(self):
        start, end = previous_calendar_month_check_out_period(today=date(2026, 7, 15))
        self.assertEqual(start, date(2026, 6, 1))
        self.assertEqual(end, date(2026, 6, 30))


class DeliverPropertyFinancialReportEmailTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.params = PropertyFinancialReportParams(
            tenant=self.tenant,
            property=self.property,
            check_out_from=date(2026, 3, 1),
            check_out_to_exclusive=date(2026, 4, 1),
        )

    @patch("apps.reservations.reports.delivery.build_property_financial_report")
    @patch("apps.reservations.reports.delivery.send_property_financial_report_email")
    def test_delivers_to_all_recipients(self, mock_send, mock_build):
        mock_build.return_value = sample_property_financial_report_result()
        mock_send.side_effect = [
            {"status": "sent", "subject": "Report A"},
            {"status": "sent", "subject": "Report B"},
        ]

        outcome = deliver_property_financial_report_email(
            self.params,
            recipients=["a@example.com", "b@example.com"],
        )

        self.assertEqual(outcome["status"], "sent")
        self.assertEqual(outcome["recipients"], ["a@example.com", "b@example.com"])
        self.assertEqual(mock_send.call_count, 2)

    def test_skips_when_no_recipient(self):
        outcome = deliver_property_financial_report_email(self.params, recipients=[])
        self.assertEqual(outcome["status"], "skipped")
        self.assertEqual(outcome["reason"], "no_recipient")
