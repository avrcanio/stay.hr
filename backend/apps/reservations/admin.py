from django.contrib import admin

from apps.core.admin import TenantScopedAdminMixin
from apps.reservations.models import (
    DocumentScanLog,
    EvisitorSubmission,
    Guest,
    IdDocument,
    MonthlyStatisticsOverride,
    Reservation,
    ReservationUnit,
)


class GuestInline(admin.TabularInline):
    model = Guest
    extra = 0
    fields = ("first_name", "last_name", "is_primary", "evisitor_status", "email")


class ReservationUnitInline(admin.TabularInline):
    model = ReservationUnit
    extra = 0


@admin.register(Reservation)
class ReservationAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "booking_code",
        "property",
        "tenant",
        "check_in",
        "check_out",
        "status",
        "booker_name",
    )
    list_filter = ("tenant", "status", "property")
    search_fields = (
        "booking_code",
        "external_id",
        "booker_name",
        "booker_email",
    )
    raw_id_fields = ("tenant", "property")
    date_hierarchy = "check_in"
    inlines = [ReservationUnitInline, GuestInline]


@admin.register(ReservationUnit)
class ReservationUnitAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("reservation", "room_name", "unit", "sort_order", "tenant")
    list_filter = ("tenant",)
    raw_id_fields = ("tenant", "reservation", "unit")


@admin.register(Guest)
class GuestAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "reservation", "tenant", "is_primary", "evisitor_status", "email")
    list_filter = ("tenant",)
    search_fields = ("name", "email", "reservation__booking_code")
    raw_id_fields = ("tenant", "reservation")


@admin.register(IdDocument)
class IdDocumentAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    tenant_field = "guest__tenant"
    list_display = ("id", "guest", "created_at")
    raw_id_fields = ("guest",)


@admin.register(DocumentScanLog)
class DocumentScanLogAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("id", "guest", "status", "method", "created_at", "tenant")
    list_filter = ("status", "tenant")
    raw_id_fields = ("tenant", "reservation", "guest")


@admin.register(MonthlyStatisticsOverride)
class MonthlyStatisticsOverrideAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Jedan zapis = cijeli mjesec; API ne zbraja rezervacije za taj tenant/godina/mjesec."""

    list_display = (
        "tenant",
        "year",
        "month",
        "revenue",
        "nights",
        "commission",
        "currency",
        "updated_at",
    )
    list_filter = ("tenant", "year")
    ordering = ("-year", "-month")
    search_fields = ("notes",)
    raw_id_fields = ("tenant",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "tenant",
                    "year",
                    "month",
                    "revenue",
                    "commission",
                    "nights",
                    "currency",
                    "notes",
                ),
                "description": (
                    "Ako postoji zapis za tenant, godinu i mjesec, mjesečna statistika "
                    "koristi ove vrijednosti umjesto zbroja iz rezervacija."
                ),
            },
        ),
    )


@admin.register(EvisitorSubmission)
class EvisitorSubmissionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("guest", "status", "registration_id", "submitted_at", "tenant")
    list_filter = ("status", "tenant")
    raw_id_fields = ("tenant", "guest")
