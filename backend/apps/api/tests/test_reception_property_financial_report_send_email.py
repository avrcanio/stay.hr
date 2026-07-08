from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.properties.models import Property
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class PropertyFinancialReportSendEmailAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
            financial_report_recipients="configured@example.com",
        )
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-API",
            external_id="ext-api",
            check_in=date(2026, 3, 10),
            check_out=date(2026, 3, 13),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Ana Anić",
            amount=Decimal("150.00"),
            commission_amount=Decimal("15.00"),
            nights_count=3,
            currency="EUR",
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Ana",
            last_name="Anić",
            nationality="HR",
            is_primary=True,
        )
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}
        self.url = "/api/v1/reception/reports/property-financial/send-email/"

    def test_requires_auth(self):
        response = self.client.post(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.api.reception_report_views.deliver_property_financial_report_email")
    def test_send_with_explicit_recipients(self, mock_deliver):
        mock_deliver.return_value = {
            "status": "sent",
            "recipients": ["ops@example.com"],
            "subject": "Financijski izvještaj",
            "reservation_count": 1,
        }

        response = self.client.post(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
                "recipients": ["ops@example.com"],
            },
            format="json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["recipients"], ["ops@example.com"])
        mock_deliver.assert_called_once()
        self.assertEqual(mock_deliver.call_args.kwargs["recipients"], ["ops@example.com"])

    @patch("apps.api.reception_report_views.deliver_property_financial_report_email")
    def test_falls_back_to_property_recipients(self, mock_deliver):
        mock_deliver.return_value = {
            "status": "sent",
            "recipients": ["configured@example.com"],
            "subject": "Financijski izvještaj",
            "reservation_count": 1,
        }

        response = self.client.post(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
            },
            format="json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        mock_deliver.assert_called_once()
        self.assertEqual(
            mock_deliver.call_args.kwargs["recipients"],
            ["configured@example.com"],
        )

    def test_no_recipient_when_property_and_body_empty(self):
        self.property.financial_report_recipients = ""
        self.property.save(update_fields=["financial_report_recipients"])

        response = self.client.post(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
            },
            format="json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "no_recipient")

    @override_settings(EMAIL_HOST="")
    @patch("apps.api.reception_report_views.deliver_property_financial_report_email")
    def test_no_smtp(self, mock_deliver):
        mock_deliver.return_value = {"status": "skipped", "reason": "no_smtp"}

        response = self.client.post(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
                "recipients": ["ops@example.com"],
            },
            format="json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "no_smtp")
