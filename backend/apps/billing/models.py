from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models

from apps.core.models import TenantScopedModel
from apps.tenants.token_encryption import decrypt_api_token, encrypt_api_token


def fiscal_certificate_upload_to(instance, filename: str) -> str:
    tenant_slug = instance.tenant.slug if instance.tenant_id else "unknown"
    return f"fiscal_certs/{tenant_slug}/{filename}"


def invoice_pdf_upload_to(instance, filename: str) -> str:
    tenant_slug = instance.tenant.slug if instance.tenant_id else "unknown"
    return f"invoices/{tenant_slug}/{instance.pk or 'draft'}/{filename}"


class TenantFiscalSettings(models.Model):
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="fiscal_settings",
    )
    is_vat_registered = models.BooleanField(
        default=False,
        help_text="Tenant is in the Croatian VAT system and must issue fiscalized guest invoices.",
    )
    issuer_oib = models.CharField(max_length=11, blank=True, default="")
    issuer_name = models.CharField(max_length=255, blank=True, default="")
    issuer_address = models.TextField(blank=True, default="")
    issuer_iban = models.CharField(max_length=34, blank=True, default="")
    business_premise_code = models.CharField(max_length=20, blank=True, default="")
    payment_device_code = models.CharField(max_length=20, blank=True, default="")
    operator_code = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Operator mark on fiscal device (e.g. OIB-1).",
    )
    accommodation_vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("13.00"),
    )
    invoice_sequence = models.PositiveIntegerField(default=0)
    certificate_file = models.FileField(
        upload_to=fiscal_certificate_upload_to,
        blank=True,
        null=True,
    )
    certificate_password_encrypted = models.TextField(blank=True, default="")
    certificate_expires_at = models.DateField(null=True, blank=True)
    use_test_endpoint = models.BooleanField(
        default=True,
        help_text="Use CIS test endpoint (cistest.apis-it.hr).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant fiscal settings"
        verbose_name_plural = "Tenant fiscal settings"

    def __str__(self) -> str:
        return f"Fiscal settings — {self.tenant}"

    @property
    def has_certificate(self) -> bool:
        return bool(self.certificate_file)

    @property
    def has_certificate_password(self) -> bool:
        return bool(self.certificate_password_encrypted)

    def set_certificate_password(self, raw: str) -> None:
        self.certificate_password_encrypted = encrypt_api_token(raw) if raw else ""

    def get_certificate_password(self) -> str:
        if not self.certificate_password_encrypted:
            return ""
        return decrypt_api_token(self.certificate_password_encrypted)

    def is_ready_for_fiscalization(self) -> bool:
        return bool(
            self.is_vat_registered
            and self.issuer_oib
            and self.issuer_name
            and self.business_premise_code
            and self.payment_device_code
            and self.has_certificate
            and self.has_certificate_password
        )


class Invoice(TenantScopedModel):
    class FiscalStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        FISCALIZED = "fiscalized", "Fiscalized"
        FAILED = "failed", "Failed"

    class PaymentMethod(models.TextChoices):
        BOOKING = "booking", "Booking"
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        TRANSFER = "transfer", "Transfer"
        OTHER = "other", "Other"

    reservation = models.OneToOneField(
        "reservations.Reservation",
        on_delete=models.CASCADE,
        related_name="invoice",
    )
    invoice_number = models.CharField(max_length=64)
    sequence_number = models.PositiveIntegerField()
    issued_at = models.DateTimeField()
    buyer_name = models.CharField(max_length=255)
    buyer_document_number = models.CharField(max_length=64, blank=True, default="")
    buyer_address = models.TextField(blank=True, default="")
    buyer_country = models.CharField(max_length=64, blank=True, default="")
    payment_method = models.CharField(
        max_length=16,
        choices=PaymentMethod.choices,
        default=PaymentMethod.OTHER,
    )
    payment_note = models.TextField(blank=True, default="")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    zki = models.CharField(max_length=32, blank=True, default="")
    jir = models.CharField(max_length=36, blank=True, default="")
    fiscal_status = models.CharField(
        max_length=16,
        choices=FiscalStatus.choices,
        default=FiscalStatus.PENDING,
    )
    fiscal_error = models.TextField(blank=True, default="")
    fiscalized_at = models.DateTimeField(null=True, blank=True)
    pdf_file = models.FileField(
        upload_to=invoice_pdf_upload_to,
        blank=True,
        null=True,
    )
    public_access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_recipient = models.EmailField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sequence_number"],
                name="billing_invoice_unique_tenant_sequence",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_number} ({self.buyer_name})"


class InvoiceLine(models.Model):
    class LineKind(models.TextChoices):
        ACCOMMODATION = "accommodation", "Accommodation"
        TOURIST_TAX_ADULT = "tourist_tax_adult", "Tourist tax — adults"
        TOURIST_TAX_CHILD = "tourist_tax_child", "Tourist tax — children"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    line_kind = models.CharField(max_length=32, choices=LineKind.choices)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.description


class FiscalizationAttempt(models.Model):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="fiscalization_attempts",
    )
    attempt_no = models.PositiveSmallIntegerField()
    fiskal_request_id = models.UUIDField(null=True, blank=True)
    success = models.BooleanField(default=False)
    request_snapshot = models.TextField(blank=True, default="")
    response_snapshot = models.TextField(blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "attempt_no"],
                name="billing_fiscal_attempt_unique_invoice_attempt",
            ),
        ]

    def __str__(self) -> str:
        return f"Fiscal attempt #{self.attempt_no} invoice={self.invoice_id}"
