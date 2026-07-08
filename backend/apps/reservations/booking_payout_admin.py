from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from apps.core.admin import TenantHostScopedAdminMixin
from apps.core.admin_forms import TenantHostScopedModelForm
from apps.reservations.booking_payout.apply import apply_booking_payout_import
from apps.reservations.booking_payout.csv_parser import BookingPayoutCsvParseError
from apps.reservations.booking_payout.preview import preview_booking_payout_csv
from apps.reservations.booking_payout.sync import (
    build_line_sync_preview,
    sync_booking_payout_import,
    sync_booking_payout_line,
)
from apps.reservations.booking_payout.types import (
    BookingPayoutSyncError,
    SyncPolicy,
    highest_warning_severity,
)
from apps.reservations.booking_payout.validate import BookingPayoutValidationError
from apps.reservations.booking_payout_models import (
    BookingPayoutImport,
    BookingPayoutImportStatus,
    BookingPayoutLine,
    BookingPayoutLineSyncResult,
    BookingPayoutMatchStatus,
    BookingPayoutWarningSeverity,
)
from apps.reservations.models import Reservation
from apps.reservations.reservation_finance import compute_owner_net, format_money_amount

_SEVERITY_COLORS = {
    BookingPayoutWarningSeverity.ERROR: "#f8d7da",
    BookingPayoutWarningSeverity.WARNING: "#fff3cd",
    BookingPayoutWarningSeverity.INFO: "#d1ecf1",
}

_SYNC_RESULT_COLORS = {
    BookingPayoutLineSyncResult.SUCCESS: "#d4edda",
    BookingPayoutLineSyncResult.NO_CHANGES: "#cce5ff",
    BookingPayoutLineSyncResult.FAILED: "#f8d7da",
}


class BookingPayoutImportAdminForm(TenantHostScopedModelForm):
    class Meta:
        model = BookingPayoutImport
        fields = ("tenant", "property_obj", "source_file")

    def clean(self):
        cleaned = super().clean()
        source_file = cleaned.get("source_file")
        tenant = cleaned.get("tenant") or getattr(self.instance, "tenant", None)
        property_obj = cleaned.get("property_obj")
        if not self.instance.pk and source_file and tenant and property_obj:
            content = source_file.read()
            source_file.seek(0)
            try:
                preview, _import_batch = preview_booking_payout_csv(
                    content,
                    tenant=tenant,
                    property_obj=property_obj,
                    filename=source_file.name,
                    persist=False,
                )
            except (BookingPayoutCsvParseError, BookingPayoutValidationError) as exc:
                raise forms.ValidationError(str(exc)) from exc
            if preview.batch_errors:
                raise forms.ValidationError("; ".join(preview.batch_errors))
            self.preview_result = preview
            self.upload_content = content
        return cleaned


class BookingPayoutLineInline(admin.TabularInline):
    model = BookingPayoutLine
    extra = 0
    can_delete = False
    readonly_fields = (
        "line_number",
        "booking_number",
        "guest_name",
        "check_in",
        "check_out",
        "gross_amount",
        "commission_amount",
        "service_fee",
        "net_amount",
        "currency",
        "match_status",
        "severity_badge",
        "sync_result_badge",
        "warnings_display",
        "reservation",
        "applied_at",
        "reservation_synced_at",
        "line_action",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Severity")
    def severity_badge(self, obj: BookingPayoutLine) -> str:
        severity = highest_warning_severity(obj.warnings)
        if not severity:
            return "—"
        color = _SEVERITY_COLORS.get(severity, "#ffffff")
        return format_html(
            '<span style="background:{}; padding:2px 6px; border-radius:4px;">{}</span>',
            color,
            severity,
        )

    @admin.display(description="Sync result")
    def sync_result_badge(self, obj: BookingPayoutLine) -> str:
        if not obj.last_sync_result:
            return "—"
        color = _SYNC_RESULT_COLORS.get(obj.last_sync_result, "#ffffff")
        return format_html(
            '<span style="background:{}; padding:2px 6px; border-radius:4px;">{}</span>',
            color,
            obj.get_last_sync_result_display(),
        )

    @admin.display(description="Action")
    def line_action(self, obj: BookingPayoutLine) -> str:
        if obj.match_status != BookingPayoutMatchStatus.MATCHED or obj.reservation_id is None:
            return "—"
        url = reverse(
            "admin:reservations_bookingpayoutimport_sync_line",
            args=[obj.import_batch_id, obj.pk],
        )
        return format_html('<a href="{}">Primijeni i ispravi</a>', url)

    @admin.display(description="Warnings")
    def warnings_display(self, obj: BookingPayoutLine) -> str:
        if not obj.warnings:
            return "—"
        parts = []
        for key, entry in obj.warnings.items():
            if not isinstance(entry, dict):
                continue
            msg = entry.get("message") or key
            parts.append(f"{key}: {msg}")
        return "; ".join(parts) if parts else "—"


@admin.register(BookingPayoutImport)
class BookingPayoutImportAdmin(TenantHostScopedAdminMixin, admin.ModelAdmin):
    form = BookingPayoutImportAdminForm
    platform_raw_id_fields = ("tenant", "uploaded_by", "applied_by")
    inlines = [BookingPayoutLineInline]
    list_display = (
        "payout_id",
        "property_obj",
        "currency",
        "status",
        "matched_count_display",
        "warning_count_display",
        "applied_count_display",
        "uploaded_by",
        "applied_by",
        "applied_at",
        "source_sha256_short",
    )
    list_filter = ("status", "tenant", "property_obj")
    search_fields = ("payout_id", "source_sha256")
    readonly_fields = (
        "payout_id",
        "payout_date",
        "currency",
        "source_sha256",
        "status",
        "revision",
        "applied_at",
        "applied_by",
        "summary_snapshot",
        "created_at",
        "matched_count_display",
        "synced_count_display",
        "warning_count_display",
        "applied_count_display",
        "error_count_display",
        "reconciliation_health_display",
    )
    actions = [
        "apply_payout_to_reservations",
        "sync_and_correct_all_matched",
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/sync-line/<int:line_id>/",
                self.admin_site.admin_view(self.sync_line_view),
                name="reservations_bookingpayoutimport_sync_line",
            ),
        ]
        return custom + urls

    def sync_line_view(self, request, object_id, line_id):
        import_batch = get_object_or_404(
            BookingPayoutImport.objects.select_related("tenant", "property_obj"),
            pk=object_id,
        )
        line = get_object_or_404(
            BookingPayoutLine.objects.select_related("reservation"),
            pk=line_id,
            import_batch_id=import_batch.pk,
        )

        if not self.has_change_permission(request, import_batch):
            raise PermissionDenied

        if not request.user.has_perm("reservations.apply_booking_payout_line"):
            raise PermissionDenied("Nemate dozvolu za sync payout linije.")

        field_diffs = build_line_sync_preview(
            line,
            policy=SyncPolicy.MANUAL_OVERRIDE,
        )
        has_invoice = False
        if line.reservation_id:
            from apps.billing.models import Invoice

            has_invoice = Invoice.objects.filter(reservation_id=line.reservation_id).exists()

        pdf_source = (
            line.reservation
            and (
                line.reservation.import_source == "booking_pdf"
                or line.reservation.financial_source == "booking_pdf"
            )
        )

        if request.method == "POST":
            try:
                expected_revision = int(request.POST.get("revision", ""))
            except (TypeError, ValueError):
                messages.error(request, "Nevažeća revision vrijednost.")
                return HttpResponseRedirect(
                    reverse(
                        "admin:reservations_bookingpayoutimport_change",
                        args=[import_batch.pk],
                    )
                )

            try:
                result = sync_booking_payout_line(
                    line.pk,
                    applied_by=request.user,
                    policy=SyncPolicy.MANUAL_OVERRIDE,
                    expected_revision=expected_revision,
                )
            except BookingPayoutSyncError as exc:
                messages.error(request, str(exc))
                return HttpResponseRedirect(
                    reverse(
                        "admin:reservations_bookingpayoutimport_change",
                        args=[import_batch.pk],
                    )
                )

            if result.result == "SUCCESS":
                messages.success(
                    request,
                    f"Linija {line.line_number} usklađena ({result.updated_fields_count} polja).",
                )
            elif result.result == "NO_CHANGES":
                messages.info(request, f"Linija {line.line_number}: nema promjena.")
            else:
                code = result.error_code.label if result.error_code else "Failed"
                messages.error(request, f"Sync nije uspio: {code}")

            return HttpResponseRedirect(
                reverse(
                    "admin:reservations_bookingpayoutimport_change",
                    args=[import_batch.pk],
                )
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "import_batch": import_batch,
            "line": line,
            "field_diffs": field_diffs,
            "has_invoice": has_invoice,
            "pdf_source": pdf_source,
            "revision": import_batch.revision,
            "title": f"Primijeni i ispravi — linija {line.line_number}",
        }
        return render(
            request,
            "admin/reservations/bookingpayoutimport/sync_line_confirm.html",
            context,
        )

    def get_fields(self, request, obj=None):
        return self._apply_host_hidden_fields(request, obj, self._payout_fields(obj))

    def _payout_fields(self, obj):
        if obj is None:
            return ("tenant", "property_obj", "source_file")
        return (
            "tenant",
            "property_obj",
            "payout_id",
            "payout_date",
            "currency",
            "source_file",
            "source_sha256",
            "status",
            "revision",
            "uploaded_by",
            "applied_by",
            "applied_at",
            "reconciliation_health_display",
            "matched_count_display",
            "synced_count_display",
            "warning_count_display",
            "applied_count_display",
            "error_count_display",
            "summary_snapshot",
            "created_at",
        )

    def has_change_permission(self, request, obj=None):
        if (
            obj is not None
            and obj.status == BookingPayoutImportStatus.APPLIED
            and not request.user.is_superuser
        ):
            return False
        return super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.status == BookingPayoutImportStatus.APPLIED:
            return list(set(readonly + [f.name for f in self.model._meta.fields]))
        if obj is not None:
            return readonly
        return ()

    def save_model(self, request, obj, form, change):
        self.apply_host_tenant(request, obj)
        if change:
            super().save_model(request, obj, form, change)
            return

        content = getattr(form, "upload_content", None)
        preview = getattr(form, "preview_result", None)
        if content is None or preview is None:
            raise forms.ValidationError("CSV upload is required.")

        _, import_batch = preview_booking_payout_csv(
            content,
            tenant=obj.tenant,
            property_obj=obj.property_obj,
            filename=form.cleaned_data["source_file"].name,
            uploaded_by=request.user,
            persist=True,
        )
        if import_batch is None:
            raise forms.ValidationError("Failed to create payout import batch.")

        self._created_import = import_batch

        duplicate_warning = BookingPayoutImport.objects.filter(
            property_obj=obj.property_obj,
            source_sha256=preview.source_sha256,
        ).exclude(pk=import_batch.pk).exists()
        if duplicate_warning:
            messages.warning(
                request,
                "A file with the same SHA-256 was previously imported for this property.",
            )

        messages.success(
            request,
            f"Parsed payout {import_batch.payout_id}: {import_batch.lines.count()} lines.",
        )

    def response_add(self, request, obj, post_url_continue=None):
        created = getattr(self, "_created_import", None)
        if created is not None:
            return HttpResponseRedirect(
                reverse("admin:reservations_bookingpayoutimport_change", args=[created.pk])
            )
        return super().response_add(request, obj, post_url_continue)

    @admin.display(description="Matched")
    def matched_count_display(self, obj: BookingPayoutImport) -> int:
        return obj.matched_count

    @admin.display(description="Synced")
    def synced_count_display(self, obj: BookingPayoutImport) -> int:
        return obj.synced_lines_count

    @admin.display(description="Reconciliation")
    def reconciliation_health_display(self, obj: BookingPayoutImport) -> str:
        pct = obj.reconciliation_health_pct
        matched = obj.matched_lines_count
        synced = obj.synced_lines_count
        warnings = obj.warning_count
        errors = obj.error_count
        return format_html(
            "<strong>{}%</strong> ({} matched · {} synced · {} warning · {} errors)",
            pct,
            matched,
            synced,
            warnings,
            errors,
        )

    @admin.display(description="Warnings")
    def warning_count_display(self, obj: BookingPayoutImport) -> int:
        return obj.warning_count

    @admin.display(description="Applied")
    def applied_count_display(self, obj: BookingPayoutImport) -> int:
        return obj.applied_count

    @admin.display(description="Errors")
    def error_count_display(self, obj: BookingPayoutImport) -> int:
        return obj.error_count

    @admin.display(description="SHA-256")
    def source_sha256_short(self, obj: BookingPayoutImport) -> str:
        sha = obj.source_sha256 or ""
        return f"{sha[:12]}…" if len(sha) > 12 else sha

    @admin.action(description="Apply payout to reservations")
    def apply_payout_to_reservations(self, request, queryset):
        applied_batches = 0
        for import_batch in queryset:
            if import_batch.status != BookingPayoutImportStatus.PARSED:
                messages.error(
                    request,
                    f"Import {import_batch.payout_id} is not PARSED (status={import_batch.status}).",
                )
                continue
            try:
                result = apply_booking_payout_import(
                    import_batch.pk,
                    applied_by=request.user,
                )
            except Exception as exc:
                messages.error(request, f"Apply failed for {import_batch.payout_id}: {exc}")
                continue
            applied_batches += 1
            messages.success(
                request,
                (
                    f"Applied {import_batch.payout_id}: "
                    f"{result.applied} reservations, {result.skipped} skipped, "
                    f"{result.warnings} warnings, {result.errors} errors "
                    f"({result.duration_ms} ms)."
                ),
            )
        if applied_batches == 0:
            messages.warning(request, "No imports were applied.")

    @admin.action(description="Primijeni i ispravi sve matched")
    def sync_and_correct_all_matched(self, request, queryset):
        if not request.user.has_perm("reservations.apply_booking_payout_line"):
            messages.error(request, "Nemate dozvolu za sync payout linija.")
            return

        synced_batches = 0
        for import_batch in queryset:
            if import_batch.status not in (
                BookingPayoutImportStatus.PARSED,
                BookingPayoutImportStatus.PARTIALLY_SYNCED,
            ):
                messages.error(
                    request,
                    f"Import {import_batch.payout_id} nije u PARSED/PARTIALLY_SYNCED "
                    f"(status={import_batch.status}).",
                )
                continue
            try:
                result = sync_booking_payout_import(
                    import_batch.pk,
                    applied_by=request.user,
                    policy=SyncPolicy.MANUAL_OVERRIDE,
                    expected_revision=import_batch.revision,
                )
            except BookingPayoutSyncError as exc:
                messages.error(
                    request,
                    f"Sync failed for {import_batch.payout_id}: {exc}",
                )
                continue
            synced_batches += 1
            messages.success(
                request,
                (
                    f"Synced {import_batch.payout_id}: "
                    f"{result.success} success, {result.no_changes} unchanged, "
                    f"{result.failed} failed ({result.duration_ms} ms)."
                ),
            )
        if synced_batches == 0:
            messages.warning(request, "No imports were synced.")


_FINANCE_FIELDSET_TITLE = "Financije (rezervacija)"
_PAYOUT_FIELDSET_TITLE = "Booking.com payout"
_RESERVATION_FINANCE_EXTENDED_ATTR = "_reservation_finance_extended"
_SELECT_RELATED_APPLIED_ATTR = "_finance_select_related_applied"

_FINANCE_FIELDSET_FIELDS = (
    "amount",
    "currency",
    "commission_percent",
    "commission_amount",
    "owner_net_display",
)
_PAYOUT_FIELDSET_FIELDS = (
    "booking_payout_received_at",
    "booking_payout_id",
    "booking_payout_net",
    "booking_payout_service_fee",
    "booking_payout_line_display",
)
_READONLY_FIELDS = _PAYOUT_FIELDSET_FIELDS + ("owner_net_display",)
_FIELDSET_EXCLUDED = frozenset(
    _FINANCE_FIELDSET_FIELDS + _PAYOUT_FIELDSET_FIELDS + ("booking_payout_line",)
)
_PAYOUT_LIST_FILTERS = ("booking_payout_received_at", "booking_payout_id")


def _dedupe_preserve_order(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _fieldsets_include_finance(fieldsets) -> bool:
    if not fieldsets:
        return False
    titles = {title for title, _ in fieldsets}
    return _FINANCE_FIELDSET_TITLE in titles and _PAYOUT_FIELDSET_TITLE in titles


def _default_reservation_fieldsets():
    other_fields = tuple(
        field.name
        for field in Reservation._meta.fields
        if field.name not in _FIELDSET_EXCLUDED
        and field.editable
        and not field.primary_key
    )
    return ((None, {"fields": other_fields}),)


def _finance_fieldsets():
    return (
        (
            _FINANCE_FIELDSET_TITLE,
            {
                "fields": _FINANCE_FIELDSET_FIELDS,
                "description": (
                    "Neto vlasniku = bruto − provizija. "
                    "Različito od Booking.com payout neta."
                ),
            },
        ),
        (
            _PAYOUT_FIELDSET_TITLE,
            {
                "fields": _PAYOUT_FIELDSET_FIELDS,
                "description": (
                    "Iz CSV payout importa. Uključuje service fee. "
                    "Ne mijenja amount/commission."
                ),
            },
        ),
    )


def _attach_display_methods(reservation_admin: admin.ModelAdmin) -> None:
    @admin.display(description="Neto vlasniku (izračunato)")
    def owner_net_display(self, obj: Reservation) -> str:
        net = compute_owner_net(obj.amount, obj.commission_amount)
        if net is None:
            return self.get_empty_value_display()
        return format_html("{} {}", format_money_amount(net), obj.currency or "")

    @admin.display(description="Payout import")
    def booking_payout_line_display(self, obj: Reservation) -> str:
        if not obj.booking_payout_line_id:
            return self.get_empty_value_display()
        line = obj.booking_payout_line
        if line is None:
            return self.get_empty_value_display()
        import_batch = line.import_batch
        if import_batch is None:
            return self.get_empty_value_display()
        url = reverse(
            "admin:reservations_bookingpayoutimport_change",
            args=[import_batch.pk],
        )
        return format_html('<a href="{}">{}</a>', url, import_batch)

    reservation_admin.owner_net_display = owner_net_display
    reservation_admin.booking_payout_line_display = booking_payout_line_display


def _extend_list_filter(reservation_admin: admin.ModelAdmin) -> None:
    existing = tuple(reservation_admin.list_filter)
    to_add = tuple(f for f in _PAYOUT_LIST_FILTERS if f not in existing)
    if to_add:
        reservation_admin.list_filter = existing + to_add


def _extend_readonly_fields(reservation_admin: admin.ModelAdmin) -> None:
    existing = tuple(getattr(reservation_admin, "readonly_fields", ()) or ())
    reservation_admin.readonly_fields = _dedupe_preserve_order(existing + _READONLY_FIELDS)


def _extend_fieldsets(reservation_admin: admin.ModelAdmin) -> None:
    if _fieldsets_include_finance(reservation_admin.fieldsets):
        return

    finance_fieldsets = _finance_fieldsets()
    existing = reservation_admin.fieldsets
    if existing is None:
        reservation_admin.fieldsets = _default_reservation_fieldsets() + finance_fieldsets
    else:
        reservation_admin.fieldsets = tuple(existing) + finance_fieldsets


def _patch_get_queryset(admin_cls: type[admin.ModelAdmin]) -> None:
    if getattr(admin_cls, _SELECT_RELATED_APPLIED_ATTR, False):
        return

    original_get_queryset = admin_cls.get_queryset

    def get_queryset(self, request):
        return original_get_queryset(self, request).select_related(
            "booking_payout_line__import_batch",
        )

    admin_cls.get_queryset = get_queryset
    setattr(admin_cls, _SELECT_RELATED_APPLIED_ATTR, True)


def extend_reservation_admin(reservation_admin: admin.ModelAdmin) -> None:
    _attach_display_methods(reservation_admin)

    if getattr(reservation_admin, _RESERVATION_FINANCE_EXTENDED_ATTR, False):
        return

    _extend_list_filter(reservation_admin)
    _extend_readonly_fields(reservation_admin)
    _extend_fieldsets(reservation_admin)
    _patch_get_queryset(reservation_admin)
    setattr(reservation_admin, _RESERVATION_FINANCE_EXTENDED_ATTR, True)
