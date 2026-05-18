from django.db import models

from apps.tenants.tokens import DEFAULT_KEY_PREFIX, generate_token, hash_token

VALID_SCOPES = frozenset(
    {
        "public:read",
        "reservations:create",
        "admin:read",
        "admin:write",
    }
)


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


class TenantDomain(models.Model):
    class DomainType(models.TextChoices):
        STAY_SUBDOMAIN = "stay_subdomain", "Stay subdomain"
        CUSTOM_DOMAIN = "custom_domain", "Custom domain"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="domains",
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


class ApiApplication(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="api_applications",
    )
    name = models.CharField(max_length=255)
    key_prefix = models.CharField(max_length=32, default=DEFAULT_KEY_PREFIX)
    public_key_hash = models.CharField(max_length=64, unique=True, db_index=True)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
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
        return raw_token

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
