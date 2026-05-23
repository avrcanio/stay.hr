from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TenantScopedModel


class Reservation(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        EXPECTED = "expected", "Expected"
        CHECKED_IN = "checked_in", "Checked in"
        CHECKED_OUT = "checked_out", "Checked out"
        CANCELED = "canceled", "Canceled"
        REFUSED = "refused", "Refused"

    OPERATIONAL_STATUSES = frozenset(
        {Status.EXPECTED, Status.CHECKED_IN, Status.CHECKED_OUT, Status.CANCELED}
    )

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    external_id = models.CharField(max_length=255, blank=True)
    legacy_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    booking_code = models.CharField(max_length=64, blank=True)
    check_in = models.DateField()
    check_out = models.DateField()
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.EXPECTED,
    )
    booking_status = models.CharField(max_length=64, blank=True)
    booker_name = models.CharField(max_length=255)
    booker_email = models.EmailField(blank=True)
    booker_phone = models.CharField(max_length=64, blank=True)
    booker_country = models.CharField(max_length=8, blank=True)
    booker_address = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="EUR")
    source = models.CharField(max_length=64, blank=True)
    import_source = models.CharField(max_length=32, blank=True)
    booked_at = models.DateTimeField(null=True, blank=True)
    units_count = models.PositiveSmallIntegerField(null=True, blank=True)
    persons_count = models.PositiveSmallIntegerField(null=True, blank=True)
    adults_count = models.PositiveSmallIntegerField(null=True, blank=True)
    children_count = models.PositiveSmallIntegerField(null=True, blank=True)
    infants_count = models.PositiveSmallIntegerField(null=True, blank=True)
    children_ages = models.CharField(max_length=128, blank=True)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_status = models.CharField(max_length=128, blank=True)
    payment_provider = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    travel_purpose = models.CharField(max_length=128, blank=True)
    booking_device = models.CharField(max_length=64, blank=True)
    nights_count = models.PositiveSmallIntegerField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    details_pending = models.BooleanField(default=False)
    imported_at = models.DateTimeField(null=True, blank=True)
    xls_imported_at = models.DateTimeField(null=True, blank=True)
    pdf_imported_at = models.DateTimeField(null=True, blank=True)
    smoobu_modified_at = models.DateTimeField(null=True, blank=True)
    smoobu_booking_id = models.CharField(max_length=64, blank=True)
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
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                condition=models.Q(external_id__gt=""),
                name="reservations_reservation_unique_tenant_external_id",
            ),
            models.UniqueConstraint(
                fields=["tenant", "legacy_id"],
                condition=models.Q(legacy_id__isnull=False),
                name="reservations_reservation_unique_tenant_legacy_id",
            ),
        ]

    def __str__(self) -> str:
        label = self.booking_code or self.external_id or str(self.pk)
        return f"{label} ({self.check_in} → {self.check_out})"


class ReservationUnit(TenantScopedModel):
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="units",
    )
    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservation_units",
    )
    legacy_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    room_name = models.CharField(max_length=256)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["reservation_id", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["reservation", "sort_order"],
                name="reservations_unit_unique_sort_order_per_reservation",
            ),
            models.UniqueConstraint(
                fields=["tenant", "legacy_id"],
                condition=models.Q(legacy_id__isnull=False),
                name="reservations_unit_unique_tenant_legacy_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reservation_id} #{self.sort_order}: {self.room_name}"


class EvisitorGuestStatus(models.TextChoices):
    NOT_SENT = "not_sent", "Nije poslano"
    PENDING = "pending", "U tijeku"
    SENT = "sent", "Poslano"
    CHECKED_OUT = "checked_out", "Odjavljeno"
    FAILED = "failed", "Neuspješno"


class Guest(TenantScopedModel):
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="guests",
    )
    legacy_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    document_number = models.CharField(max_length=64, blank=True)
    nationality = models.CharField(max_length=2, blank=True)
    sex = models.CharField(max_length=16, blank=True)
    address = models.TextField(blank=True)
    date_of_issue = models.DateField(null=True, blank=True)
    date_of_expiry = models.DateField(null=True, blank=True)
    issuing_authority = models.CharField(max_length=255, blank=True)
    personal_id_number = models.CharField(max_length=64, blank=True)
    document_additional_number = models.CharField(max_length=64, blank=True)
    additional_personal_id_number = models.CharField(max_length=64, blank=True)
    document_code = models.CharField(max_length=16, blank=True)
    document_type = models.CharField(max_length=64, blank=True)
    document_country = models.CharField(max_length=64, blank=True)
    document_country_iso2 = models.CharField(max_length=2, blank=True)
    document_country_iso3 = models.CharField(max_length=3, blank=True)
    document_country_numeric = models.CharField(max_length=8, blank=True)
    mrz_raw_text = models.TextField(blank=True)
    mrz_verified = models.BooleanField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    evisitor_status = models.CharField(max_length=16, blank=True, default="")
    evisitor_registration_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["reservation_id", "-is_primary", "last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["reservation"],
                condition=models.Q(is_primary=True),
                name="reservations_guest_unique_primary_per_reservation",
            ),
            models.UniqueConstraint(
                fields=["tenant", "legacy_id"],
                condition=models.Q(legacy_id__isnull=False),
                name="reservations_guest_unique_tenant_legacy_id",
            ),
        ]

    def __str__(self) -> str:
        return self.name or f"{self.first_name} {self.last_name}".strip()

    def save(self, *args, **kwargs):
        full = f"{self.first_name} {self.last_name}".strip()
        if full:
            self.name = full
        super().save(*args, **kwargs)


class EvisitorSubmission(TenantScopedModel):
    guest = models.ForeignKey(
        Guest,
        on_delete=models.CASCADE,
        related_name="evisitor_submissions",
    )
    legacy_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    registration_id = models.UUIDField()
    status = models.CharField(max_length=16)
    submitted_at = models.DateTimeField(null=True, blank=True)
    error_user_message = models.TextField(blank=True)
    error_system_message = models.TextField(blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "legacy_id"],
                condition=models.Q(legacy_id__isnull=False),
                name="reservations_evisitor_unique_tenant_legacy_id",
            ),
        ]

    def __str__(self) -> str:
        return f"eVisitor {self.status} guest={self.guest_id}"


def id_document_face_upload_to(instance, filename: str) -> str:
    return f"id_documents/faces/{filename}"


def id_document_signature_upload_to(instance, filename: str) -> str:
    return f"id_documents/signatures/{filename}"


def id_document_front_upload_to(instance, filename: str) -> str:
    if getattr(instance, "_passport_photo", False):
        return f"id_documents/passports/{filename}"
    return f"id_documents/{filename}"


def id_document_back_upload_to(instance, filename: str) -> str:
    return f"id_documents/{filename}"


class IdDocument(models.Model):
    guest = models.ForeignKey(
        Guest,
        on_delete=models.CASCADE,
        related_name="id_documents",
    )
    image_path = models.CharField(max_length=500, blank=True, default="")
    face_photo = models.ImageField(
        upload_to=id_document_face_upload_to,
        null=True,
        blank=True,
    )
    signature_photo = models.ImageField(
        upload_to=id_document_signature_upload_to,
        null=True,
        blank=True,
    )
    front_photo = models.ImageField(
        upload_to=id_document_front_upload_to,
        null=True,
        blank=True,
    )
    back_photo = models.ImageField(
        upload_to=id_document_back_upload_to,
        null=True,
        blank=True,
    )
    extracted_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self) -> str:
        return f"IdDocument #{self.pk} guest={self.guest_id}"


class DocumentScanStatus(models.TextChoices):
    OK = "ok", "OK"
    FAILED = "failed", "Failed"


def id_recognition_sample_upload_to(instance, filename: str) -> str:
    tenant_id = getattr(instance, "tenant_id", None) or "unknown"
    return f"id_recognition_samples/{tenant_id}/{filename}"


class IdRecognitionSampleSource(models.TextChoices):
    MRZ_PLUS = "mrz_plus", "MRZ Plus"
    MRZ_LEGACY = "mrz_legacy", "MRZ Legacy"


class IdRecognitionSample(TenantScopedModel):
    """Cropped document images for ID recognition model training."""

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="id_recognition_samples",
    )
    guest = models.ForeignKey(
        Guest,
        on_delete=models.CASCADE,
        related_name="id_recognition_samples",
    )
    image = models.ImageField(upload_to=id_recognition_sample_upload_to)
    source = models.CharField(
        max_length=32,
        choices=IdRecognitionSampleSource.choices,
        default=IdRecognitionSampleSource.MRZ_PLUS,
    )
    document_type = models.CharField(max_length=32, blank=True, default="")
    raw_mrz = models.TextField(blank=True, default="")
    ocr_text = models.TextField(blank=True, default="")
    device_id = models.CharField(max_length=128, blank=True, default="")
    parsed_snapshot = models.JSONField(default=dict, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self) -> str:
        return f"IdRecognitionSample #{self.pk} guest={self.guest_id} source={self.source}"


class DocumentScanLog(TenantScopedModel):
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="document_scan_logs",
    )
    guest = models.ForeignKey(
        Guest,
        on_delete=models.CASCADE,
        related_name="document_scan_logs",
    )
    status = models.CharField(max_length=16, choices=DocumentScanStatus.choices)
    method = models.CharField(max_length=8, blank=True, default="")
    device_id = models.CharField(max_length=128, blank=True, default="")
    scanned_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    suggested_fields = models.JSONField(default=dict, blank=True)
    corrected_fields = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self) -> str:
        return f"DocumentScanLog #{self.pk} guest={self.guest_id}"


class MonthlyStatisticsOverride(TenantScopedModel):
    """Ručni mjesečni prihod/noći/provizija; nadjačava automatski zbroj iz rezervacija."""

    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    revenue = models.DecimalField(max_digits=12, decimal_places=2)
    commission = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    nights = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="EUR")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "-month"]
        verbose_name = "Ručna statistika (mjesec)"
        verbose_name_plural = "Ručna statistika (mjesec)"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "year", "month"],
                name="reservations_monthly_stats_override_tenant_year_month_uniq",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.year}-{self.month:02d} — "
            f"{self.revenue} {self.currency}, {self.nights} noći"
        )
