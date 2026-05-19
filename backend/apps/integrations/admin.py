from django.contrib import admin

from apps.core.admin import TenantScopedAdminMixin
from apps.integrations.models import (
    ChannelRatePlan,
    ChannexAriOutbox,
    ChannexBookingRevision,
    IntegrationConfig,
    RatePlanDay,
    UnitAvailabilityDay,
)


@admin.register(IntegrationConfig)
class IntegrationConfigAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("provider", "tenant", "property", "is_active", "updated_at")
    list_filter = ("provider", "is_active", "tenant")
    search_fields = ("tenant__name", "tenant__slug", "property__slug")
    raw_id_fields = ("tenant", "property")
    readonly_fields = ("config_encrypted", "created_at", "updated_at")

    def get_changeform_initial_data(self, request):
        return super().get_changeform_initial_data(request) or {}

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field)
        if obj and obj.config_encrypted:
            obj.config = obj.get_config_dict()
        return obj

    def save_model(self, request, obj, form, change):
        plain = dict(form.cleaned_data.get("config") or {})
        obj.set_config_dict(plain)
        super().save_model(request, obj, form, change)


@admin.register(ChannelRatePlan)
class ChannelRatePlanAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("unit", "code", "title", "default_rate", "currency", "is_active")
    list_filter = ("property", "is_active")
    search_fields = ("unit__code", "code", "channex_rate_plan_id")


@admin.register(UnitAvailabilityDay)
class UnitAvailabilityDayAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("unit", "date", "availability", "synced_at")
    list_filter = ("unit__property",)
    date_hierarchy = "date"


@admin.register(RatePlanDay)
class RatePlanDayAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "rate_plan",
        "date",
        "rate",
        "min_stay_arrival",
        "stop_sell",
        "synced_at",
    )
    list_filter = ("rate_plan__property", "stop_sell")
    date_hierarchy = "date"


@admin.register(ChannexAriOutbox)
class ChannexAriOutboxAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("property", "kind", "status", "sent_at", "created_at")
    list_filter = ("kind", "status", "property")
    readonly_fields = ("values", "channex_task_ids", "error_message")


@admin.register(ChannexBookingRevision)
class ChannexBookingRevisionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("revision_id", "booking_id", "channex_status", "reservation", "acknowledged_at")
    search_fields = ("revision_id", "booking_id")
