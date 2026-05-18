from django.contrib import admin

from apps.integrations.models import IntegrationConfig


@admin.register(IntegrationConfig)
class IntegrationConfigAdmin(admin.ModelAdmin):
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
