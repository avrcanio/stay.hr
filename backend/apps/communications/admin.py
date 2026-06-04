from django.contrib import admin

from apps.core.admin import TenantScopedAdminMixin
from apps.communications.models import GuestMessageDraft, GuestOutboundMessage


class ReadOnlyAuditAdminMixin:
    """Audit tables: view-only in Django admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GuestMessageDraft)
class GuestMessageDraftAdmin(
    ReadOnlyAuditAdminMixin,
    TenantScopedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "id",
        "reservation",
        "intent",
        "channel",
        "language",
        "edited_display",
        "api_application",
        "created_at",
        "sent_at",
        "tenant",
    )
    list_filter = ("tenant", "intent", "channel", "language")
    search_fields = (
        "reservation__booking_code",
        "reservation__external_id",
        "reservation__booker_name",
        "llm_body_text",
        "final_body_text",
    )
    raw_id_fields = ("tenant", "reservation", "api_application")
    readonly_fields = (
        "tenant",
        "reservation",
        "intent",
        "hint",
        "llm_body_text",
        "final_body_text",
        "language",
        "channel",
        "llm_model",
        "prompt_version",
        "api_application",
        "created_at",
        "sent_at",
        "edited_display",
    )
    date_hierarchy = "created_at"

    @admin.display(boolean=True, description="Edited")
    def edited_display(self, obj: GuestMessageDraft) -> bool:
        return obj.edited


@admin.register(GuestOutboundMessage)
class GuestOutboundMessageAdmin(
    ReadOnlyAuditAdminMixin,
    TenantScopedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "id",
        "reservation",
        "channel",
        "status",
        "to_email",
        "to_phone",
        "api_application",
        "created_at",
        "tenant",
    )
    list_filter = ("tenant", "channel", "status")
    search_fields = (
        "reservation__booking_code",
        "reservation__external_id",
        "to_email",
        "to_phone",
        "body_text",
    )
    raw_id_fields = ("tenant", "reservation", "draft", "api_application")
    readonly_fields = (
        "tenant",
        "reservation",
        "draft",
        "channel",
        "body_text",
        "status",
        "to_email",
        "to_phone",
        "wa_me_url",
        "error_message",
        "api_application",
        "created_at",
    )
    date_hierarchy = "created_at"
