from django.contrib import admin
from django.utils.html import format_html

from apps.core.admin import SuperuserOnlyAdminMixin, TenantScopedAdminMixin
from apps.integrations.admin.forms import IntegrationConfigAdminForm
from apps.integrations.config_secrets import (
    credentials_complete,
    credentials_status_summary,
)
from apps.integrations.models import (
    ChannelRatePlan,
    ChannexAriOutbox,
    ChannexBookingRevision,
    ChannexMessage,
    ChannexReview,
    IntegrationConfig,
    RatePlanDay,
    UnitAvailabilityDay,
    WhatsAppInboundRouting,
)

CHANNEL_MANAGER_HELP = (
    "For outbound reservation sync, set Tenant → Reception settings → "
    "channel_manager (channex / none). "
    "Credentials are stored per tenant in Integration configs (this form), not on the tenant page."
)

ADD_PROVIDER_HELP = (
    "Select a provider above — the form reloads automatically and shows credential fields. "
    "You can also save once, then reopen the record to edit credentials."
)


@admin.register(IntegrationConfig)
class IntegrationConfigAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    form = IntegrationConfigAdminForm
    class Media:
        js = ("integrations/admin/integration_config_provider.js",)

    list_display = (
        "provider",
        "tenant",
        "property",
        "routing_key",
        "is_platform_default",
        "credentials_status_short",
        "is_active",
        "updated_at",
    )
    list_filter = ("provider", "is_active", "tenant")
    search_fields = ("tenant__name", "tenant__slug", "property__slug", "routing_key")
    raw_id_fields = ("tenant", "property")
    readonly_fields = (
        "credentials_status_display",
        "created_at",
        "updated_at",
    )

    def get_form(self, request, obj=None, **kwargs):
        # Fieldsets list custom credential fields; only pass model fields to
        # modelform_factory so it does not raise FieldError before __init__ runs.
        kwargs["fields"] = IntegrationConfigAdminForm.Meta.fields
        base_form = super().get_form(request, obj, **kwargs)
        admin_request = request

        class RequestAwareIntegrationConfigForm(base_form):
            def __init__(self, *args, **form_kwargs):
                form_kwargs["admin_request"] = admin_request
                super().__init__(*args, **form_kwargs)

        RequestAwareIntegrationConfigForm.__name__ = base_form.__name__
        RequestAwareIntegrationConfigForm.__module__ = base_form.__module__
        return RequestAwareIntegrationConfigForm

    def get_fieldsets(self, request, obj=None):
        provider = self._resolve_provider_for_fieldsets(request, obj)
        base_description = CHANNEL_MANAGER_HELP
        if obj is None and not provider:
            base_description = f"{CHANNEL_MANAGER_HELP} {ADD_PROVIDER_HELP}"
        base = (
            None,
            {
                "fields": ("tenant", "property", "provider", "routing_key", "is_active"),
                "description": base_description,
            },
        )
        credentials = (
            "Credentials",
            {
                "fields": self._credential_field_names(provider),
            },
        )
        settings = (
            "Settings",
            {
                "fields": self._settings_field_names(provider),
            },
        )
        mapping = (
            "Mapping (JSON)",
            {
                "fields": self._mapping_field_names(provider),
                "classes": ("collapse",),
            },
        )
        meta_fields: list[str] = ["credentials_status_display"]
        if obj is not None:
            meta_fields.extend(["created_at", "updated_at"])
        meta = (
            "Meta",
            {
                "fields": tuple(meta_fields),
            },
        )
        fieldsets = [base]
        if provider:
            if self._credential_field_names(provider):
                fieldsets.append(credentials)
            if self._settings_field_names(provider):
                fieldsets.append(settings)
            if self._mapping_field_names(provider):
                fieldsets.append(mapping)
        fieldsets.append(meta)
        return fieldsets

    def _resolve_provider_for_fieldsets(self, request, obj: IntegrationConfig | None) -> str:
        if obj and obj.provider:
            return obj.provider
        post_provider = str(request.POST.get("provider") or "")
        if post_provider:
            return post_provider
        return str(request.GET.get("provider") or "")

    def _credential_field_names(self, provider: str) -> tuple[str, ...]:
        if not provider:
            return ()
        mapping = {
            IntegrationConfig.Provider.CHANNEX: ("api_key", "webhook_secret"),
            IntegrationConfig.Provider.WHATSAPP: (),
            IntegrationConfig.Provider.EVISITOR: ("password", "api_key"),
        }
        return mapping.get(provider, ())

    def _settings_field_names(self, provider: str) -> tuple[str, ...]:
        if not provider:
            return ()
        mapping = {
            IntegrationConfig.Provider.CHANNEX: (
                "environment",
                "base_url",
                "property_id",
                "sync_property_slug",
                "certification_property_slug",
                "use_generated_ari",
            ),
            IntegrationConfig.Provider.WHATSAPP: (
                "phone_number_id",
                "display_phone_number",
                "waba_id",
                "auto_reply",
                "whatsapp_templates_json",
            ),
            IntegrationConfig.Provider.EVISITOR: (
                "enabled",
                "env",
                "base_url",
                "username",
                "facility_code",
                "default_arrival_organisation",
                "default_offered_service_type",
                "default_payment_category",
                "default_stay_time_from",
                "default_stay_time_until",
            ),
        }
        return mapping.get(provider, ())

    def _mapping_field_names(self, provider: str) -> tuple[str, ...]:
        if not provider:
            return ()
        mapping = {
            IntegrationConfig.Provider.CHANNEX: (
                "room_types_json",
                "booking_test_rooms_json",
            ),
        }
        return mapping.get(provider, ())

    @admin.display(description="Credentials", boolean=True)
    def credentials_status_short(self, obj: IntegrationConfig) -> bool:
        if not obj.pk:
            return False
        return credentials_complete(obj.provider, obj.get_config_dict())

    @admin.display(description="Credentials status")
    def credentials_status_display(self, obj: IntegrationConfig | None) -> str:
        if obj is None or not obj.pk:
            return "—"
        summary = credentials_status_summary(obj.provider, obj.get_config_dict())
        if credentials_complete(obj.provider, obj.get_config_dict()):
            return format_html('<span style="color:#2e7d32">{}</span>', summary)
        return format_html('<span style="color:#b00020">{}</span>', summary)


@admin.register(ChannelRatePlan)
class ChannelRatePlanAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("unit", "sales_channel", "code", "title", "default_rate", "currency", "is_active")
    list_filter = ("property", "sales_channel", "is_active")
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
    list_filter = ("channex_status",)
    search_fields = ("revision_id", "booking_id")
    readonly_fields = ("revision_id", "booking_id", "channex_status", "acknowledged_at")


@admin.register(ChannexMessage)
class ChannexMessageAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "channex_message_id",
        "direction",
        "sender",
        "reservation",
        "channex_booking_id",
        "created_at",
    )
    list_filter = ("direction", "sender", "have_attachment")
    search_fields = ("channex_message_id", "channex_booking_id", "body")
    readonly_fields = (
        "integration",
        "reservation",
        "channex_booking_id",
        "message_thread_id",
        "channex_message_id",
        "direction",
        "sender",
        "body",
        "have_attachment",
        "raw_payload",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WhatsAppInboundRouting)
class WhatsAppInboundRoutingAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "routing_method",
        "message",
        "resolved_tenant",
        "resolved_reservation",
        "created_at",
    )
    list_filter = ("status", "routing_method")
    search_fields = ("message__wamid", "message__wa_id", "message__body", "notes")
    readonly_fields = (
        "message",
        "tenant",
        "status",
        "routing_method",
        "candidate_reservations",
        "resolved_tenant",
        "resolved_reservation",
        "resolved_at",
        "resolved_by",
        "notes",
        "created_at",
        "updated_at",
    )
    raw_id_fields = ("resolved_tenant", "resolved_reservation", "resolved_by")
    actions = ["manual_link_selected"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Manual link to reservation (set resolved_reservation first)")
    def manual_link_selected(self, request, queryset):
        from apps.integrations.whatsapp.platform_inbound_router import manual_link_routing
        from apps.integrations.whatsapp.tasks import process_inbound_message

        linked = 0
        for routing in queryset.select_related("message", "resolved_reservation"):
            if routing.resolved_reservation_id is None:
                continue
            manual_link_routing(
                routing=routing,
                reservation=routing.resolved_reservation,
                user=request.user,
            )
            process_inbound_message.delay(routing.message_id)
            linked += 1
        self.message_user(request, f"Linked {linked} routing row(s).")


@admin.register(ChannexReview)
class ChannexReviewAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "channex_review_id",
        "ota",
        "ota_reservation_id",
        "booking_code_display",
        "overall_score",
        "is_replied",
        "is_hidden",
        "reservation",
        "received_at",
    )
    list_select_related = ("reservation",)
    list_filter = ("ota", "is_replied", "is_hidden")
    search_fields = (
        "channex_review_id",
        "channex_booking_id",
        "ota_reservation_id",
        "guest_name",
        "content",
    )
    readonly_fields = (
        "integration",
        "reservation",
        "channex_review_id",
        "channex_booking_id",
        "ota",
        "ota_reservation_id",
        "ota_review_id",
        "guest_name",
        "content",
        "reply",
        "overall_score",
        "scores",
        "tags",
        "is_replied",
        "is_hidden",
        "expired_at",
        "received_at",
        "reply_sent_at",
        "reply_scheduled_at",
        "raw_payload",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "integration",
                    "reservation",
                    "channex_review_id",
                    "channex_booking_id",
                    "ota",
                    "ota_reservation_id",
                    "ota_review_id",
                    "guest_name",
                    "overall_score",
                    "is_replied",
                    "is_hidden",
                    "received_at",
                    "expired_at",
                    "reply_sent_at",
                    "reply_scheduled_at",
                ),
            },
        ),
        (
            "Content",
            {
                "fields": ("content", "reply", "scores", "tags"),
            },
        ),
        (
            "Raw payload",
            {
                "classes": ("collapse",),
                "fields": ("raw_payload", "created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Booking code")
    def booking_code_display(self, obj: ChannexReview) -> str:
        if obj.reservation_id and obj.reservation:
            return obj.reservation.booking_code or str(obj.reservation_id)
        return "—"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
