from __future__ import annotations

from django.db import models

from apps.core.models import TenantScopedModel


class GuestMessageIntent(models.TextChoices):
    CHECKIN = "checkin", "Check-in"
    REPLY = "reply", "Reply"
    CUSTOM = "custom", "Custom"


class GuestMessageChannel(models.TextChoices):
    EMAIL = "email", "Email"
    WHATSAPP = "whatsapp", "WhatsApp"


class GuestOutboundMessageStatus(models.TextChoices):
    HANDOFF_WHATSAPP = "handoff_whatsapp", "WhatsApp handoff"
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class GuestMessageDraft(TenantScopedModel):
    """LLM compose attempt and optional send audit for a reservation."""

    reservation = models.ForeignKey(
        "reservations.Reservation",
        on_delete=models.CASCADE,
        related_name="guest_message_drafts",
    )
    intent = models.CharField(
        max_length=16,
        choices=GuestMessageIntent.choices,
    )
    hint = models.TextField(blank=True, default="")
    llm_body_text = models.TextField(blank=True, default="")
    final_body_text = models.TextField(blank=True, default="")
    language = models.CharField(max_length=8, blank=True, default="")
    channel = models.CharField(
        max_length=16,
        choices=GuestMessageChannel.choices,
        blank=True,
        default="",
    )
    llm_model = models.CharField(max_length=64, blank=True, default="")
    prompt_version = models.CharField(max_length=32, blank=True, default="")
    api_application = models.ForeignKey(
        "tenants.ApiApplication",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guest_message_drafts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "reservation", "-created_at"]),
        ]
        verbose_name = "Guest message draft"
        verbose_name_plural = "Guest message drafts"

    def __str__(self) -> str:
        channel = self.channel or "—"
        return (
            f"Draft #{self.pk} {self.intent} ({channel}) "
            f"res={self.reservation_id}"
        )

    @property
    def edited(self) -> bool:
        llm = (self.llm_body_text or "").strip()
        final = (self.final_body_text or "").strip()
        if not llm or not final:
            return False
        return llm != final


class GuestOutboundMessage(TenantScopedModel):
    """Outbound guest message audit (email send or WhatsApp handoff)."""

    reservation = models.ForeignKey(
        "reservations.Reservation",
        on_delete=models.CASCADE,
        related_name="guest_outbound_messages",
    )
    draft = models.ForeignKey(
        GuestMessageDraft,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_messages",
    )
    channel = models.CharField(max_length=16, choices=GuestMessageChannel.choices)
    body_text = models.TextField()
    status = models.CharField(
        max_length=32,
        choices=GuestOutboundMessageStatus.choices,
    )
    to_email = models.EmailField(blank=True, default="")
    to_phone = models.CharField(max_length=64, blank=True, default="")
    wa_me_url = models.URLField(blank=True, default="", max_length=512)
    error_message = models.TextField(blank=True, default="")
    api_application = models.ForeignKey(
        "tenants.ApiApplication",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guest_outbound_messages",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "reservation", "-created_at"]),
            models.Index(fields=["draft"]),
        ]
        verbose_name = "Guest outbound message"
        verbose_name_plural = "Guest outbound messages"

    def __str__(self) -> str:
        return (
            f"Outbound #{self.pk} {self.channel} {self.status} "
            f"res={self.reservation_id}"
        )
