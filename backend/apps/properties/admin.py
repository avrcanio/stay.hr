from django.contrib import admin

from apps.core.admin import TenantScopedAdminMixin
from apps.properties.models import Property, Unit


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 0
    fields = ("code", "name", "capacity_adults", "capacity_children", "is_active")


@admin.register(Property)
class PropertyAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "tenant", "updated_at")
    list_filter = ("tenant",)
    search_fields = ("name", "slug", "tenant__name", "tenant__slug")
    prepopulated_fields = {"slug": ("name",)}
    raw_id_fields = ("tenant",)
    inlines = [UnitInline]


@admin.register(Unit)
class UnitAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "property",
        "tenant",
        "capacity_adults",
        "is_active",
    )
    list_filter = ("tenant", "is_active", "property")
    search_fields = ("code", "name", "property__name")
    raw_id_fields = ("tenant", "property")
