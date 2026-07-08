from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.properties.models import Property
from apps.reservations.reports.tasks import send_property_financial_reports_monthly
from apps.tenants.models import Tenant


@override_settings(
    PROPERTY_FINANCIAL_REPORT_EMAIL_ENABLED=True,
    EMAIL_HOST="smtp.example.com",
)
class SendPropertyFinancialReportsMonthlyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
            financial_report_recipients="owner@example.com",
        )

    @override_settings(PROPERTY_FINANCIAL_REPORT_EMAIL_ENABLED=False)
    def test_disabled(self):
        result = send_property_financial_reports_monthly()
        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "disabled")

    @override_settings(EMAIL_HOST="")
    def test_no_smtp(self):
        result = send_property_financial_reports_monthly()
        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "no_smtp")

    @patch("apps.reservations.reports.tasks.deliver_property_financial_report_email")
    @patch("apps.reservations.reports.tasks.previous_calendar_month_check_out_period")
    def test_sends_for_configured_properties(self, mock_period, mock_deliver):
        mock_period.return_value = (date(2026, 6, 1), date(2026, 6, 30))
        mock_deliver.return_value = {
            "status": "sent",
            "recipients": ["owner@example.com"],
        }

        result = send_property_financial_reports_monthly()

        self.assertTrue(result["sent"])
        self.assertEqual(len(result["sent_properties"]), 1)
        self.assertEqual(result["sent_properties"][0]["property_slug"], "uzorita")
        mock_deliver.assert_called_once()
        params = mock_deliver.call_args.args[0]
        self.assertEqual(params.check_out_from, date(2026, 6, 1))
        self.assertEqual(params.check_out_to_exclusive, date(2026, 7, 1))

    @patch("apps.reservations.reports.tasks.deliver_property_financial_report_email")
    @patch("apps.reservations.reports.tasks.previous_calendar_month_check_out_period")
    def test_skips_properties_without_recipients(self, mock_period, mock_deliver):
        mock_period.return_value = (date(2026, 6, 1), date(2026, 6, 30))
        self.property.financial_report_recipients = ""
        self.property.save(update_fields=["financial_report_recipients"])

        result = send_property_financial_reports_monthly()

        self.assertFalse(result["sent"])
        mock_deliver.assert_not_called()
