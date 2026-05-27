from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from apps.billing.models import FiscalizationAttempt, Invoice, InvoiceLine, TenantFiscalSettings
from apps.billing.services.issue import get_fiscal_settings_for_reservation, refresh_invoice_buyer_from_reservation
from apps.billing.services.pdf import render_invoice_pdf
from apps.billing.tasks import fiscalize_invoice
from apps.core.admin import SuperuserOnlyAdminMixin
from apps.tenants.models import Tenant


class TenantFiscalSettingsInlineForm(forms.ModelForm):
    certificate_password = forms.CharField(
        label="Certificate password",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Password for the .p12 certificate. Leave blank to keep the current password.",
    )

    class Meta:
        model = TenantFiscalSettings
        fields = (
            "is_vat_registered",
            "issuer_oib",
            "issuer_name",
            "issuer_address",
            "issuer_iban",
            "business_premise_code",
            "payment_device_code",
            "operator_code",
            "accommodation_vat_rate",
            "certificate_file",
            "certificate_password",
            "certificate_expires_at",
            "use_test_endpoint",
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data.get("certificate_password")
        if password:
            instance.set_certificate_password(password)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class TenantFiscalSettingsInline(admin.StackedInline):
    model = TenantFiscalSettings
    form = TenantFiscalSettingsInlineForm
    extra = 0
    max_num = 1
    can_delete = False
    readonly_fields = (
        "invoice_sequence",
        "has_certificate_display",
        "has_certificate_password_display",
        "updated_at",
    )
    fields = (
        "is_vat_registered",
        "issuer_oib",
        "issuer_name",
        "issuer_address",
        "issuer_iban",
        "business_premise_code",
        "payment_device_code",
        "operator_code",
        "accommodation_vat_rate",
        "invoice_sequence",
        "certificate_file",
        "certificate_password",
        "has_certificate_display",
        "has_certificate_password_display",
        "certificate_expires_at",
        "use_test_endpoint",
        "updated_at",
    )

    @admin.display(description="Certificate uploaded", boolean=True)
    def has_certificate_display(self, obj: TenantFiscalSettings | None) -> bool:
        if obj is None or not obj.pk:
            return False
        return obj.has_certificate

    @admin.display(description="Certificate password set", boolean=True)
    def has_certificate_password_display(self, obj: TenantFiscalSettings | None) -> bool:
        if obj is None or not obj.pk:
            return False
        return obj.has_certificate_password


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = (
        "sort_order",
        "line_kind",
        "description",
        "quantity",
        "unit_price",
        "vat_rate",
        "vat_amount",
        "line_total",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.action(description="Retry fiscalization")
def retry_fiscalization(modeladmin, request, queryset):
    count = 0
    for invoice in queryset:
        fiscalize_invoice.delay(invoice.pk)
        count += 1
    modeladmin.message_user(
        request,
        f"Queued fiscalization for {count} invoice(s).",
        level=messages.SUCCESS,
    )


@admin.action(description="Regeneriraj PDF")
def regenerate_invoice_pdf(modeladmin, request, queryset):
    count = 0
    for invoice in queryset.select_related("tenant", "reservation"):
        refresh_invoice_buyer_from_reservation(invoice)
        settings = get_fiscal_settings_for_reservation(invoice.reservation)
        render_invoice_pdf(invoice, settings)
        count += 1
    modeladmin.message_user(
        request,
        f"Regenerated PDF for {count} invoice(s).",
        level=messages.SUCCESS,
    )


@admin.register(Invoice)
class InvoiceAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "tenant",
        "buyer_name",
        "total",
        "currency",
        "fiscal_status",
        "issued_at",
    )
    list_filter = ("fiscal_status", "tenant")
    search_fields = ("invoice_number", "buyer_name", "jir", "zki", "reservation__booking_code")
    readonly_fields = (
        "tenant",
        "reservation",
        "invoice_number",
        "sequence_number",
        "issued_at",
        "buyer_name",
        "buyer_document_number",
        "buyer_address",
        "buyer_country",
        "payment_method",
        "payment_note",
        "subtotal",
        "vat_amount",
        "total",
        "currency",
        "zki",
        "jir",
        "fiscal_status",
        "fiscal_error",
        "fiscalized_at",
        "pdf_link",
        "public_access_token",
        "email_sent_at",
        "email_recipient",
        "created_at",
        "updated_at",
    )
    inlines = [InvoiceLineInline]
    actions = [retry_fiscalization, regenerate_invoice_pdf]

    @admin.display(description="PDF")
    def pdf_link(self, obj: Invoice | None) -> str:
        if obj is None or not obj.pk or not obj.pdf_file:
            return "—"
        return format_html('<a href="{}" target="_blank">Download PDF</a>', obj.pdf_file.url)

    def has_add_permission(self, request):
        return False


@admin.register(FiscalizationAttempt)
class FiscalizationAttemptAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("invoice", "attempt_no", "success", "created_at")
    list_filter = ("success",)
    readonly_fields = (
        "invoice",
        "attempt_no",
        "success",
        "request_snapshot",
        "response_snapshot",
        "error_message",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


def register_tenant_fiscal_inline():
    try:
        tenant_admin = admin.site._registry[Tenant]
    except KeyError:
        return
    if TenantFiscalSettingsInline not in tenant_admin.inlines:
        tenant_admin.inlines = list(tenant_admin.inlines) + [TenantFiscalSettingsInline]


register_tenant_fiscal_inline()
