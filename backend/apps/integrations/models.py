from django.db import models

from apps.core.models import TenantScopedModel


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
    config = models.JSONField(default=dict, blank=True)
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
