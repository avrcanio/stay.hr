import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.billing.models import FiscalizationAttempt, Invoice, InvoiceLine, TenantFiscalSettings
from apps.billing.services.fisk1 import FiscalResult
from apps.billing.tasks import fiscalize_invoice
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class FiscalizeInvoicePlatformTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Platform Tenant", slug="uzorita")
        self.settings = TenantFiscalSettings.objects.create(
            tenant=self.tenant,
            is_vat_registered=True,
            issuer_oib="12345678901",
            issuer_name="Test Issuer",
            business_premise_code="PP1",
            payment_device_code="1",
        )
        self.settings.set_certificate_password("secret")
        self.settings.save()

        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=Property.objects.create(
                tenant=self.tenant,
                name="P",
                slug="p",
            ),
            check_in=datetime(2026, 4, 15).date(),
            check_out=datetime(2026, 4, 16).date(),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Guest",
            amount=Decimal("100.00"),
        )
        self.invoice = Invoice.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            invoice_number="1-PP1-1",
            sequence_number=1,
            issued_at=datetime(2026, 4, 16, 10, 0, 0),
            buyer_name="Guest",
            subtotal=Decimal("88.50"),
            vat_amount=Decimal("11.50"),
            total=Decimal("100.00"),
            zki="abc123",
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            sort_order=1,
            line_kind=InvoiceLine.LineKind.ACCOMMODATION,
            description="Noćenje",
            quantity=Decimal("1"),
            unit_price=Decimal("88.50"),
            vat_rate=Decimal("13.00"),
            vat_amount=Decimal("11.50"),
            line_total=Decimal("100.00"),
        )

        cert_file = MagicMock()
        cert_file.read.return_value = b"fake-p12"
        self.settings.certificate_file = cert_file

    @override_settings(FISKAL_EXECUTION_ENABLED=True)
    @patch("apps.billing.services.fisk1.connector.render_invoice_pdf")
    @patch("apps.billing.services.fiskal_platform.submit.fiscalize_via_platform")
    def test_fiscalize_invoice_uses_platform_when_enabled(self, mock_fiscalize, _pdf):
        request_id = uuid.uuid4()
        mock_fiscalize.return_value = FiscalResult(
            jir="ABC-DEF-123",
            request_snapshot=f"fiskal_request_id={request_id}",
            response_snapshot="status=accepted",
            fiskal_request_id=request_id,
        )

        result = fiscalize_invoice.run(self.invoice.pk)

        self.assertEqual(result["status"], "fiscalized")
        self.assertEqual(result["jir"], "ABC-DEF-123")
        mock_fiscalize.assert_called_once()

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.jir, "ABC-DEF-123")
        self.assertEqual(self.invoice.fiscal_status, Invoice.FiscalStatus.FISCALIZED)

        attempt = FiscalizationAttempt.objects.get(invoice=self.invoice)
        self.assertTrue(attempt.success)
        self.assertEqual(attempt.fiskal_request_id, request_id)

    @override_settings(FISKAL_EXECUTION_ENABLED=False)
    @patch("apps.billing.services.fisk1.connector.render_invoice_pdf")
    @patch("apps.billing.services.fisk1.connector.Fisk1Connector.fiscalize")
    def test_fiscalize_invoice_uses_fisk1_when_disabled(self, mock_fiscalize, _pdf):
        mock_fiscalize.return_value = FiscalResult(jir="LEGACY-JIR")

        result = fiscalize_invoice.run(self.invoice.pk)

        self.assertEqual(result["status"], "fiscalized")
        self.assertEqual(result["jir"], "LEGACY-JIR")
        mock_fiscalize.assert_called_once()
