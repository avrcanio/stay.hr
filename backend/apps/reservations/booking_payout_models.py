from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TenantScopedModel
from apps.reservations.models import Reservation


def booking_payout_import_upload_to(instance, filename: str) -> str:
    tenant_slug = instance.tenant.slug if instance.tenant_id else "unknown"
    payout_id = (instance.payout_id or "unknown").strip() or "unknown"
    return f"booking_payouts/{tenant_slug}/{payout_id}.csv"


class BookingPayoutImportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PARSED = "parsed", "Parsed"
    PARTIALLY_SYNCED = "partially_synced", "Partially synced"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"


class BookingPayoutMatchStatus(models.TextChoices):
    MATCHED = "matched", "Matched"
    UNMATCHED = "unmatched", "Unmatched"
    DUPLICATE = "duplicate", "Duplicate"


class BookingPayoutWarningSeverity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


class BookingPayoutLineSyncResult(models.TextChoices):
    SUCCESS = "success", "Success"
    NO_CHANGES = "no_changes", "No changes"
    FAILED = "failed", "Failed"


class BookingPayoutImport(TenantScopedModel):
    property_obj = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="booking_payout_imports",
    )
    payout_id = models.CharField(max_length=64, db_index=True)
    payout_date = models.DateField()
    currency = models.CharField(max_length=3)
    source_file = models.FileField(upload_to=booking_payout_import_upload_to)
    source_sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20,
        choices=BookingPayoutImportStatus.choices,
        default=BookingPayoutImportStatus.PENDING,
    )
    revision = models.PositiveIntegerField(default=1)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_payout_uploads",
    )
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_payout_applies",
    )
    applied_at = models.DateTimeField(null=True, blank=True, db_index=True)
    summary_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["property_obj", "payout_id"],
                name="reservations_bookingpayoutimport_unique_property_payout",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.payout_id} ({self.payout_date}) — {self.status}"

    @property
    def matched_count(self) -> int:
        return self.lines.filter(match_status=BookingPayoutMatchStatus.MATCHED).count()

    @property
    def warning_count(self) -> int:
        return sum(1 for line in self.lines.all() if line.has_warning_severity)

    @property
    def applied_count(self) -> int:
        return self.lines.filter(applied_at__isnull=False).count()

    @property
    def error_count(self) -> int:
        return sum(
            1
            for line in self.lines.all()
            if line.match_status == BookingPayoutMatchStatus.UNMATCHED
            or line.has_error_severity
        )

    @property
    def matched_lines_count(self) -> int:
        return self.lines.filter(match_status=BookingPayoutMatchStatus.MATCHED).count()

    @property
    def synced_lines_count(self) -> int:
        return self.lines.filter(
            match_status=BookingPayoutMatchStatus.MATCHED,
            reservation_synced_at__isnull=False,
        ).count()

    @property
    def is_fully_synced(self) -> bool:
        matched = self.matched_lines_count
        return matched > 0 and self.synced_lines_count == matched

    @property
    def reconciliation_health_pct(self) -> int:
        matched = self.matched_lines_count
        if matched == 0:
            return 0
        return round(100 * self.synced_lines_count / matched)

    def ensure_applied_audit(self) -> bool:
        """Backfill applied_at/applied_by when batch is APPLIED and fully confirmed."""
        if self.applied_at is not None:
            return False
        if self.status != BookingPayoutImportStatus.APPLIED or not self.is_fully_synced:
            return False

        line = (
            self.lines.filter(reservation_synced_at__isnull=False)
            .order_by("reservation_synced_at")
            .first()
        )
        if line is None:
            line = self.lines.filter(applied_at__isnull=False).order_by("applied_at").first()
        if line is None:
            return False

        self.applied_at = line.reservation_synced_at or line.applied_at or timezone.now()
        self.applied_by_id = (
            line.reservation_synced_by_id or self.uploaded_by_id
        )
        self.save(update_fields=["applied_at", "applied_by"])
        return True


class BookingPayoutLine(models.Model):
    import_batch = models.ForeignKey(
        BookingPayoutImport,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    line_number = models.PositiveIntegerField()
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_payout_lines",
    )
    booking_number = models.CharField(max_length=64, db_index=True)
    guest_name = models.CharField(max_length=255, blank=True)
    check_in = models.DateField()
    check_out = models.DateField()
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    service_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    reservation_status = models.CharField(max_length=32, blank=True)
    match_status = models.CharField(
        max_length=16,
        choices=BookingPayoutMatchStatus.choices,
        default=BookingPayoutMatchStatus.UNMATCHED,
    )
    source_row = models.JSONField(default=dict)
    warnings = models.JSONField(default=dict, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    reservation_synced_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reservation_synced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_payout_line_syncs",
    )
    reservation_sync_reason = models.CharField(max_length=64, blank=True)
    last_sync_result = models.CharField(
        max_length=16,
        choices=BookingPayoutLineSyncResult.choices,
        blank=True,
    )
    reservation_before_sync = models.JSONField(default=dict, blank=True)
    reservation_after_sync = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["line_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["import_batch", "line_number"],
                name="reservations_bookingpayoutline_unique_import_line",
            ),
        ]
        permissions = [
            (
                "apply_booking_payout_line",
                "Can sync booking payout to reservation",
            ),
        ]

    def __str__(self) -> str:
        return f"Line {self.line_number}: {self.booking_number} ({self.match_status})"

    @property
    def has_warning_severity(self) -> bool:
        from apps.reservations.booking_payout.types import highest_warning_severity

        return highest_warning_severity(self.warnings) == BookingPayoutWarningSeverity.WARNING

    @property
    def has_error_severity(self) -> bool:
        from apps.reservations.booking_payout.types import highest_warning_severity

        return highest_warning_severity(self.warnings) == BookingPayoutWarningSeverity.ERROR
