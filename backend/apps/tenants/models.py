from datetime import time

from django.conf import settings
from django.db import models

from apps.tenants.token_encryption import decrypt_api_token, encrypt_api_token
from apps.tenants.tokens import DEFAULT_KEY_PREFIX, generate_token, hash_token

VALID_SCOPES = frozenset(
    {
        "public:read",
        "reservations:create",
        "reception:read",
        "reception:write",
        "admin:read",
        "admin:write",
    }
)

# Hospira / recepcija (Flutter tablet) — device token scopes per plan.
RECEPTION_DEVICE_SCOPES = [
    "reception:read",
    "reception:write",
    "public:read",
]

PUBLIC_BOOKING_SCOPES = [
    "public:read",
    "reservations:create",
]


class Tenant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    timezone = models.CharField(max_length=64, default="UTC")
    default_language = models.CharField(max_length=10, default="en")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class TenantReceptionSettings(models.Model):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="reception_settings",
    )
    auto_checkout_enabled = models.BooleanField(default=False)
    auto_checkout_time = models.TimeField(default=time(10, 0))
    auto_checkout_last_run_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Tenant reception settings"

    def __str__(self) -> str:
        return f"Reception settings — {self.tenant}"


class TenantDomain(models.Model):
    class DomainType(models.TextChoices):
        STAY_SUBDOMAIN = "stay_subdomain", "Stay subdomain"
        CUSTOM_DOMAIN = "custom_domain", "Custom domain"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="domains",
    )
    property = models.ForeignKey(
        "properties.Property",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tenant_domains",
    )
    domain = models.CharField(max_length=255, unique=True)
    domain_type = models.CharField(max_length=20, choices=DomainType.choices)
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["domain"]

    def __str__(self) -> str:
        return self.domain


class TenantMembership(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant_memberships",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tenant__name", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant"],
                name="tenants_membership_unique_user_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.tenant}"


class ApiApplication(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="api_applications",
    )
    name = models.CharField(max_length=255)
    key_prefix = models.CharField(max_length=32, default=DEFAULT_KEY_PREFIX)
    public_key_hash = models.CharField(max_length=64, unique=True, db_index=True)
    token_encrypted = models.TextField(blank=True, default="")
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    fcm_token = models.CharField(max_length=512, blank=True, default="")
    fcm_token_updated_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.tenant.slug})"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        super().clean()
        if not isinstance(self.scopes, list):
            raise ValidationError({"scopes": "Scopes must be a list."})
        invalid = set(self.scopes) - VALID_SCOPES
        if invalid:
            raise ValidationError(
                {"scopes": f"Unknown scopes: {', '.join(sorted(invalid))}"}
            )

    def set_token(self, raw_token: str | None = None) -> str:
        if raw_token is None:
            raw_token = generate_token(self.key_prefix)
        self.public_key_hash = hash_token(raw_token)
        self.token_encrypted = encrypt_api_token(raw_token)
        return raw_token

    def get_stored_token(self) -> str | None:
        if not self.token_encrypted:
            return None
        return decrypt_api_token(self.token_encrypted)

    def regenerate_token(self) -> str:
        raw = self.set_token()
        self.full_clean()
        self.save(
            update_fields=["public_key_hash", "token_encrypted", "updated_at"],
        )
        return raw

    @classmethod
    def create_with_token(
        cls,
        *,
        tenant: Tenant,
        name: str,
        scopes: list[str] | None = None,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        **kwargs,
    ) -> tuple["ApiApplication", str]:
        app = cls(
            tenant=tenant,
            name=name,
            key_prefix=key_prefix,
            scopes=scopes if scopes is not None else [],
            **kwargs,
        )
        raw_token = app.set_token()
        app.full_clean()
        app.save()
        return app, raw_token
