from __future__ import annotations

from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.reception_views import ReceptionReadView
from apps.billing.models import Invoice, TenantFiscalSettings
from apps.billing.services.pdf import render_invoice_html
from apps.reservations.models import Reservation


class InvoiceSerializerMixin:
    @staticmethod
    def serialize_invoice(invoice: Invoice) -> dict:
        pdf_url = invoice.pdf_file.url if invoice.pdf_file else None
        return {
            "id": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "issued_at": invoice.issued_at.isoformat(),
            "buyer_name": invoice.buyer_name,
            "payment_method": invoice.payment_method,
            "payment_note": invoice.payment_note,
            "subtotal": str(invoice.subtotal),
            "vat_amount": str(invoice.vat_amount),
            "total": str(invoice.total),
            "currency": invoice.currency,
            "zki": invoice.zki,
            "jir": invoice.jir,
            "fiscal_status": invoice.fiscal_status,
            "fiscal_error": invoice.fiscal_error,
            "fiscalized_at": invoice.fiscalized_at.isoformat() if invoice.fiscalized_at else None,
            "pdf_url": pdf_url,
            "public_access_token": str(invoice.public_access_token),
            "email_sent_at": invoice.email_sent_at.isoformat() if invoice.email_sent_at else None,
            "lines": [
                {
                    "description": line.description,
                    "quantity": str(line.quantity),
                    "unit_price": str(line.unit_price),
                    "vat_rate": str(line.vat_rate),
                    "vat_amount": str(line.vat_amount),
                    "line_total": str(line.line_total),
                    "line_kind": line.line_kind,
                }
                for line in invoice.lines.order_by("sort_order", "id")
            ],
        }


class ReservationInvoiceView(ReceptionReadView, InvoiceSerializerMixin, APIView):
    def get(self, request, pk: int):
        reservation = get_object_or_404(
            Reservation.objects.for_tenant(request.tenant),
            pk=pk,
        )
        invoice = getattr(reservation, "invoice", None)
        if invoice is None:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.serialize_invoice(invoice))


class InvoicePdfView(ReceptionReadView, APIView):
    def get(self, request, invoice_id: int):
        invoice = get_object_or_404(
            Invoice.objects.for_tenant(request.tenant).select_related("tenant"),
            pk=invoice_id,
        )
        if not invoice.pdf_file:
            return Response({"detail": "PDF not available."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(
            invoice.pdf_file.open("rb"),
            as_attachment=True,
            filename=invoice.pdf_file.name.rsplit("/", 1)[-1],
            content_type="application/pdf",
        )


class PublicInvoiceHtmlView(InvoiceSerializerMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, public_access_token):
        invoice = get_object_or_404(
            Invoice.objects.select_related("tenant", "reservation", "reservation__property"),
            public_access_token=public_access_token,
        )
        settings, _ = TenantFiscalSettings.objects.get_or_create(tenant=invoice.tenant)
        html = render_invoice_html(invoice, settings)
        return HttpResponse(html)


class PublicInvoicePdfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, public_access_token):
        invoice = get_object_or_404(
            Invoice.objects.select_related("tenant"),
            public_access_token=public_access_token,
        )
        if not invoice.pdf_file:
            return Response({"detail": "PDF not available."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(
            invoice.pdf_file.open("rb"),
            as_attachment=True,
            filename=f"racun-{invoice.invoice_number.replace('/', '-')}.pdf",
            content_type="application/pdf",
        )
