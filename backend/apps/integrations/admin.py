from django.contrib import admin

from apps.integrations.models import IntegrationConfig


@admin.register(IntegrationConfig)
class IntegrationConfigAdmin(admin.ModelAdmin):
    list_display = ("provider", "tenant", "property", "is_active", "updated_at")
    list_filter = ("provider", "is_active", "tenant")
    search_fields = ("tenant__name", "tenant__slug", "property__slug")
    raw_id_fields = ("tenant", "property")
