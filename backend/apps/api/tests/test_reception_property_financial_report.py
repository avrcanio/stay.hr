from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.properties.models import Property
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class PropertyFinancialReportAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
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
        self.url = "/api/v1/reception/reports/property-financial/"

    def test_requires_auth(self):
        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_success_json_shape(self):
        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["meta"]["property_slug"], "uzorita")
        self.assertEqual(data["meta"]["check_out_from"], "2026-03-01")
        self.assertEqual(data["meta"]["check_out_to"], "2026-03-31")
        self.assertEqual(data["meta"]["currency"], "EUR")
        self.assertEqual(data["meta"]["max_period_days"], 90)
        self.assertEqual(data["totals"]["reservation_count"], 1)
        self.assertEqual(data["totals"]["gross"], "150.00")
        self.assertEqual(data["totals"]["commission"], "15.00")
        self.assertEqual(data["totals"]["net"], "135.00")
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["booking_code"], "BK-API")
        self.assertEqual(row["gross"], "150.00")
        self.assertEqual(row["net"], "135.00")
        self.assertEqual(len(row["guests"]), 1)
        self.assertEqual(row["guests"][0]["nationality_iso2"], "HR")

    def test_excludes_reservation_outside_period(self):
        self.reservation.check_out = date(2026, 4, 2)
        self.reservation.save(update_fields=["check_out", "updated_at"])

        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["totals"]["reservation_count"], 0)

    def test_period_invalid(self):
        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "not-a-date",
                "check_out_to": "2026-03-31",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "period_invalid")

    @override_settings(PROPERTY_FINANCIAL_REPORT_MAX_DAYS=30)
    def test_period_too_long(self):
        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-01-01",
                "check_out_to": "2026-03-31",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["code"], "period_too_long")
        self.assertEqual(data["max_days"], 30)

    def test_property_required_for_multi_property_tenant(self):
        Property.objects.create(
            tenant=self.tenant,
            name="Second",
            slug="second",
        )
        response = self.client.get(
            self.url,
            {
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["code"], "property_required")
        self.assertIn("detail", data)

    def test_read_only_scope_allowed(self):
        _, read_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Read only",
            scopes=["reception:read"],
        )
        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
            },
            HTTP_AUTHORIZATION=f"Bearer {read_token}",
        )
        self.assertEqual(response.status_code, 200)

    def test_format_pdf_download(self):
        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
                "format": "pdf",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("property-financial-uzorita-2026-03-01_2026-03-31.pdf", response["Content-Disposition"])
        payload = b"".join(response.streaming_content)
        self.assertTrue(payload.startswith(b"%PDF"))

    def test_format_xlsx_download(self):
        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
                "format": "xlsx",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("property-financial-uzorita-2026-03-01_2026-03-31.xlsx", response["Content-Disposition"])
        self.assertGreater(len(b"".join(response.streaming_content)), 100)

    def test_format_invalid(self):
        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
                "format": "csv",
            },
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "format_invalid")
