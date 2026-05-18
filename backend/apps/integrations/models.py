from typing import Any

from django.db import models

from apps.core.models import TenantScopedModel
from apps.integrations.encryption import decrypt_config, encrypt_config


class IntegrationConfig(TenantScopedModel):
    class Provider(models.TextChoices):
        BOOKING = "booking", "Booking"
        EMAIL = "email", "Email"
        ICAL = "ical", "iCal"
        EVISITOR = "evisitor", "eVisitor"
        OTHER = "other", "Other"

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="integration_configs",
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Legacy/plaintext fallback; novi zapisi koriste config_encrypted.",
    )
    config_encrypted = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider", "property_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "property"],
                name="integrations_config_unique_tenant_provider_property",
            ),
        ]

    def __str__(self) -> str:
        scope = self.property.slug if self.property_id else "tenant"
        return f"{self.get_provider_display()} ({self.tenant_id}, {scope})"

    def get_config_dict(self) -> dict[str, Any]:
        if self.config_encrypted:
            return decrypt_config(self.config_encrypted)
        return dict(self.config or {})

    def set_config_dict(self, data: dict[str, Any]) -> None:
        self.config = {}
        self.config_encrypted = encrypt_config(data) if data else ""
