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
        CHANNEX = "channex", "Channex"
        SMOOBU = "smoobu", "Smoobu"
        WHATSAPP = "whatsapp", "WhatsApp"
        OTHER = "other", "Other"

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="integration_configs",
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    routing_key = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Meta phone_number_id for WhatsApp tenant routing.",
    )
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
            models.UniqueConstraint(
                fields=["provider", "routing_key"],
                condition=models.Q(routing_key__gt=""),
                name="integrations_config_unique_provider_routing_key",
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


class ChannexBookingRevision(TenantScopedModel):
    """Tracks processed Channex booking revisions (idempotency + audit)."""

    revision_id = models.CharField(max_length=36, unique=True)
    booking_id = models.CharField(max_length=36, db_index=True)
    reservation = models.ForeignKey(
        "reservations.Reservation",
        on_delete=models.CASCADE,
        related_name="channex_revisions",
    )
    channex_status = models.CharField(max_length=32, blank=True)
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-acknowledged_at"]
        indexes = [
            models.Index(fields=["tenant", "booking_id"]),
        ]

    def __str__(self) -> str:
        return f"Channex revision {self.revision_id} → reservation {self.reservation_id}"


class ChannelRatePlan(TenantScopedModel):
    """Maps stay.hr unit + rate code to Channex rate plan UUID."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="channel_rate_plans",
    )
    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.CASCADE,
        related_name="channel_rate_plans",
    )
    code = models.CharField(max_length=32)
    title = models.CharField(max_length=128, blank=True)
    channex_room_type_id = models.CharField(max_length=36)
    channex_rate_plan_id = models.CharField(max_length=36)
    default_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="GBP")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["property_id", "unit_id", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "property", "unit", "code"],
                name="integrations_rateplan_unique_tenant_property_unit_code",
            ),
            models.UniqueConstraint(
                fields=["tenant", "channex_rate_plan_id"],
                name="integrations_rateplan_unique_tenant_channex_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.unit.code}/{self.code} → {self.channex_rate_plan_id[:8]}"


class UnitAvailabilityDay(TenantScopedModel):
    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.CASCADE,
        related_name="availability_days",
    )
    date = models.DateField()
    availability = models.PositiveSmallIntegerField(default=1)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "unit_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "unit", "date"],
                name="integrations_unitavail_unique_tenant_unit_date",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "unit", "synced_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.unit.code} {self.date}: {self.availability}"


class RatePlanDay(TenantScopedModel):
    rate_plan = models.ForeignKey(
        ChannelRatePlan,
        on_delete=models.CASCADE,
        related_name="days",
    )
    date = models.DateField()
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    min_stay_arrival = models.PositiveSmallIntegerField(null=True, blank=True)
    min_stay_through = models.PositiveSmallIntegerField(null=True, blank=True)
    max_stay = models.PositiveSmallIntegerField(null=True, blank=True)
    stop_sell = models.BooleanField(default=False)
    closed_to_arrival = models.BooleanField(default=False)
    closed_to_departure = models.BooleanField(default=False)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "rate_plan_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "rate_plan", "date"],
                name="integrations_rateplanday_unique_tenant_plan_date",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "rate_plan", "synced_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.rate_plan} {self.date}: {self.rate}"


class ChannexAriOutbox(TenantScopedModel):
    class Kind(models.TextChoices):
        AVAILABILITY = "availability", "Availability"
        RESTRICTIONS = "restrictions", "Rates & restrictions"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="channex_ari_outbox",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    values = models.JSONField(default=list)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    channex_task_ids = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "property", "kind", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.status} ({len(self.values)} values)"


class UnitRateDay(TenantScopedModel):
    """Canonical per-unit daily rate for Smoobu (one price per apartment per day)."""

    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.CASCADE,
        related_name="rate_days",
    )
    date = models.DateField()
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    min_stay = models.PositiveSmallIntegerField(null=True, blank=True)
    smoobu_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "unit_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "unit", "date"],
                name="integrations_unitrateday_unique_tenant_unit_date",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "unit", "smoobu_synced_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.unit.code} {self.date}: {self.rate}"


class UnitAvailabilityBlock(TenantScopedModel):
    """Smoobu blocked-booking (channel 11) created via Hospira reception."""

    class CreatedVia(models.TextChoices):
        HOSPIRA = "hospira", "Hospira"

    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.CASCADE,
        related_name="availability_blocks",
    )
    reservation = models.ForeignKey(
        "reservations.Reservation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="smoobu_blocks",
    )
    check_in = models.DateField()
    check_out = models.DateField()
    smoobu_booking_id = models.CharField(max_length=64)
    created_via = models.CharField(
        max_length=16,
        choices=CreatedVia.choices,
        default=CreatedVia.HOSPIRA,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["check_in", "unit_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "smoobu_booking_id"],
                name="integrations_unitblock_unique_tenant_smoobu_id",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "unit", "check_in"]),
        ]

    def __str__(self) -> str:
        return f"{self.unit.code} block {self.check_in}..{self.check_out}"


class WhatsAppMessage(TenantScopedModel):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    integration = models.ForeignKey(
        IntegrationConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_messages",
    )
    reservation = models.ForeignKey(
        "reservations.Reservation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_messages",
    )
    wamid = models.CharField(max_length=128, unique=True)
    wa_id = models.CharField(max_length=32, db_index=True)
    phone_number_id = models.CharField(max_length=32, blank=True)
    direction = models.CharField(max_length=16, choices=Direction.choices)
    message_type = models.CharField(max_length=32, blank=True)
    body = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "wa_id", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.direction} {self.wamid} ({self.wa_id})"
