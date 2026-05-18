from django.db import models

from apps.core.models import TenantScopedModel


class IntegrationConfig(TenantScopedModel):
    class Provider(models.TextChoices):
        BOOKING = "booking", "Booking"
        EMAIL = "email", "Email"
        ICAL = "ical", "iCal"
        EVISITOR = "evisitor", "eVisitor"
        OTHER = "other", "Other"

    provider = models.CharField(max_length=20, choices=Provider.choices)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider"],
                name="integrations_config_unique_tenant_provider",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_provider_display()} ({self.tenant_id})"
