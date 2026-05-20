"""Read-only mirrors of Uzorita legacy tables (unmanaged)."""

from django.db import models


class LegacyRoom(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=16)
    room_type_id = models.BigIntegerField()
    is_active = models.BooleanField()

    class Meta:
        managed = False
        db_table = "rooms_room"


class LegacyPropertyInfo(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=64)
    name_i18n = models.JSONField()
    address_i18n = models.JSONField()
    evisitor_facility_code = models.CharField(max_length=32)
    is_active = models.BooleanField()

    class Meta:
        managed = False
        db_table = "rooms_propertyinfo"


class LegacyReservation(models.Model):
    id = models.BigAutoField(primary_key=True)
    external_id = models.CharField(max_length=128)
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    status = models.CharField(max_length=32)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    currency = models.CharField(max_length=3)
    booker_name = models.CharField(max_length=255)
    booked_at = models.DateTimeField(null=True)
    booking_status = models.CharField(max_length=64)
    units_count = models.PositiveSmallIntegerField(null=True)
    persons_count = models.PositiveSmallIntegerField(null=True)
    adults_count = models.PositiveSmallIntegerField(null=True)
    children_count = models.PositiveSmallIntegerField(null=True)
    children_ages = models.CharField(max_length=128)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    payment_status = models.CharField(max_length=128)
    payment_provider = models.CharField(max_length=255)
    notes = models.TextField()
    booker_country = models.CharField(max_length=8)
    travel_purpose = models.CharField(max_length=128)
    booking_device = models.CharField(max_length=64)
    nights_count = models.PositiveSmallIntegerField(null=True)
    canceled_at = models.DateTimeField(null=True)
    booker_address = models.TextField()
    booker_phone = models.CharField(max_length=64)
    import_source = models.CharField(max_length=32)
    details_pending = models.BooleanField()
    imported_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "reception_reservation"


class LegacyReservationUnit(models.Model):
    id = models.BigAutoField(primary_key=True)
    reservation_id = models.BigIntegerField()
    sort_order = models.PositiveSmallIntegerField()
    room_name = models.CharField(max_length=256)
    room_type_id = models.BigIntegerField(null=True)
    room_id = models.BigIntegerField(null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    class Meta:
        managed = False
        db_table = "reception_reservationunit"


class LegacyGuest(models.Model):
    id = models.BigAutoField(primary_key=True)
    reservation_id = models.BigIntegerField()
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    date_of_birth = models.DateField(null=True)
    document_number = models.CharField(max_length=64)
    nationality = models.CharField(max_length=2)
    sex = models.CharField(max_length=16)
    address = models.TextField()
    date_of_issue = models.DateField(null=True)
    date_of_expiry = models.DateField(null=True)
    issuing_authority = models.CharField(max_length=255)
    personal_id_number = models.CharField(max_length=64)
    document_additional_number = models.CharField(max_length=64)
    additional_personal_id_number = models.CharField(max_length=64)
    document_code = models.CharField(max_length=16)
    document_type = models.CharField(max_length=64)
    document_country = models.CharField(max_length=64)
    document_country_iso2 = models.CharField(max_length=2)
    document_country_iso3 = models.CharField(max_length=3)
    document_country_numeric = models.CharField(max_length=8)
    mrz_raw_text = models.TextField()
    mrz_verified = models.BooleanField(null=True)
    is_primary = models.BooleanField()
    evisitor_status = models.CharField(max_length=16)
    evisitor_registration_id = models.UUIDField(null=True)

    class Meta:
        managed = False
        db_table = "reception_guest"


class LegacyIdDocument(models.Model):
    id = models.BigAutoField(primary_key=True)
    guest_id = models.BigIntegerField()
    image_path = models.CharField(max_length=500)
    face_photo = models.CharField(max_length=100)
    signature_photo = models.CharField(max_length=100)
    front_photo = models.CharField(max_length=100)
    back_photo = models.CharField(max_length=100)
    extracted_payload = models.JSONField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "reception_iddocument"


class LegacyEvisitorSubmission(models.Model):
    id = models.BigAutoField(primary_key=True)
    guest_id = models.BigIntegerField()
    registration_id = models.UUIDField()
    status = models.CharField(max_length=16)
    submitted_at = models.DateTimeField(null=True)
    error_user_message = models.TextField()
    error_system_message = models.TextField()
    request_payload = models.JSONField()
    response_payload = models.JSONField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "reception_evisitorsubmission"


class LegacyMonthlyStatisticsOverride(models.Model):
    id = models.BigAutoField(primary_key=True)
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    revenue = models.DecimalField(max_digits=12, decimal_places=2)
    commission = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    nights = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    notes = models.TextField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "reception_monthlystatisticsoverride"
