from django.db import models

from apps.core.models import TenantScopedModel


class Property(TenantScopedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64)
    address = models.TextField(blank=True)
    contact = models.JSONField(default=dict, blank=True)
    branding = models.JSONField(default=dict, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    language = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                name="properties_property_unique_tenant_slug",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Unit(TenantScopedModel):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="units",
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    capacity_adults = models.PositiveSmallIntegerField(default=2)
    capacity_children = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "property", "code"],
                name="properties_unit_unique_tenant_property_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"
