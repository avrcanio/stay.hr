from django.contrib import admin, messages
from django import forms

from apps.tenants.models import VALID_SCOPES, ApiApplication, Tenant, TenantDomain


class TenantDomainInline(admin.TabularInline):
    model = TenantDomain
    extra = 0


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "status",
        "timezone",
        "default_language",
        "updated_at",
    )
    list_filter = ("status",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TenantDomainInline]


@admin.register(TenantDomain)
class TenantDomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "domain_type", "is_primary", "is_verified")
    list_filter = ("domain_type", "is_primary", "is_verified")
    search_fields = ("domain", "tenant__name", "tenant__slug")
    raw_id_fields = ("tenant",)


class ApiApplicationAdminForm(forms.ModelForm):
    scopes = forms.MultipleChoiceField(
        choices=[(s, s) for s in sorted(VALID_SCOPES)],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Flutter apps should use public:read and optionally reservations:create only.",
    )

    class Meta:
        model = ApiApplication
        fields = ("tenant", "name", "key_prefix", "scopes", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and isinstance(self.instance.scopes, list):
            self.initial["scopes"] = self.instance.scopes

    def clean_scopes(self):
        return list(self.cleaned_data.get("scopes") or [])


@admin.register(ApiApplication)
class ApiApplicationAdmin(admin.ModelAdmin):
    form = ApiApplicationAdminForm
    list_display = ("name", "tenant", "key_prefix", "is_active", "last_used_at", "created_at")
    list_filter = ("is_active", "tenant")
    search_fields = ("name", "tenant__name", "tenant__slug")
    raw_id_fields = ("tenant",)
    readonly_fields = ("last_used_at", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly.append("public_key_hash")
        return readonly

    def save_model(self, request, obj, form, change):
        if change:
            obj.full_clean()
            obj.save()
            return

        raw_token = obj.set_token()
        obj.full_clean()
        obj.save()
        self.message_user(
            request,
            f"API application created. Copy this token now — it will not be shown again:\n\n{raw_token}",
            level=messages.WARNING,
        )
