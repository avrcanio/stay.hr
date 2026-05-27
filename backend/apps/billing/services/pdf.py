from __future__ import annotations

import base64
import io
from decimal import Decimal

import qrcode
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from apps.billing.models import Invoice, InvoiceLine, TenantFiscalSettings
from apps.billing.services.qr import build_invoice_qr_url


def _format_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}".replace(".", ",")


def _qr_data_uri(invoice: Invoice) -> str:
    url = build_invoice_qr_url(invoice)
    if not url:
        return ""
    qr = qrcode.QRCode(border=1, box_size=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def invoice_template_context(invoice: Invoice, settings: TenantFiscalSettings) -> dict:
    lines = list(invoice.lines.order_by("sort_order", "id"))
    return {
        "invoice": invoice,
        "settings": settings,
        "lines": lines,
        "formatted_lines": [
            {
                "description": line.description,
                "quantity": f"{line.quantity.quantize(Decimal('0.01')):.0f}"
                if line.quantity == line.quantity.to_integral_value()
                else f"{line.quantity:.2f}",
                "unit_price": _format_money(line.unit_price),
                "vat_rate": _format_money(line.vat_rate),
                "vat_amount": _format_money(line.vat_amount),
                "line_total": _format_money(line.line_total),
            }
            for line in lines
        ],
        "subtotal": _format_money(invoice.subtotal),
        "vat_amount": _format_money(invoice.vat_amount),
        "total": _format_money(invoice.total),
        "issued_at_display": invoice.issued_at.strftime("%d.%m.%Y %H:%M"),
        "jir_display": invoice.jir or "u obradi",
        "zki_display": invoice.zki,
        "operator_code": settings.operator_code or settings.issuer_oib,
        "qr_data_uri": _qr_data_uri(invoice),
        "tourist_tax_clause": (
            "Turistička pristojba ne podliježe oporezivanju sukladno čl. 33. st. 3. Zakona o PDV-u."
        ),
    }


def render_invoice_html(invoice: Invoice, settings: TenantFiscalSettings) -> str:
    context = invoice_template_context(invoice, settings)
    return render_to_string("billing/invoice.html", context)


def render_invoice_pdf(invoice: Invoice, settings: TenantFiscalSettings) -> None:
    html = render_invoice_html(invoice, settings)
    buffer = io.BytesIO()
    pdf = pisa.CreatePDF(html, dest=buffer, encoding="UTF-8")
    if pdf.err:
        raise RuntimeError("Failed to generate invoice PDF.")
    filename = f"invoice-{invoice.invoice_number.replace('/', '-')}.pdf"
    invoice.pdf_file.save(filename, ContentFile(buffer.getvalue()), save=True)
