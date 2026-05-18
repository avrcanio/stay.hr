from django.db import models

from apps.core.models import TenantScopedModel


class Reservation(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    external_id = models.CharField(max_length=255, blank=True)
    booking_code = models.CharField(max_length=64, blank=True)
    check_in = models.DateField()
    check_out = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    booker_name = models.CharField(max_length=255)
    booker_email = models.EmailField(blank=True)
    booker_phone = models.CharField(max_length=32, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="EUR")
    source = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-check_in", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "booking_code"],
                condition=models.Q(booking_code__gt=""),
                name="reservations_reservation_unique_tenant_booking_code",
            ),
        ]

    def __str__(self) -> str:
        label = self.booking_code or self.external_id or str(self.pk)
        return f"{label} ({self.check_in} → {self.check_out})"


class Guest(TenantScopedModel):
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="guests",
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    # document_type / document_number — add when guest ID capture is implemented
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
