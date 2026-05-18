# Generated manually for Uzorita legacy migration

import django.db.models.deletion
from django.db import migrations, models


def map_booking_status_to_operational(apps, schema_editor):
    Reservation = apps.get_model("reservations", "Reservation")
    mapping = {
        "pending": "expected",
        "confirmed": "expected",
        "cancelled": "canceled",
    }
    for old, new in mapping.items():
        Reservation.objects.filter(status=old).update(status=new)


def split_guest_names(apps, schema_editor):
    Guest = apps.get_model("reservations", "Guest")
    for guest in Guest.objects.all().iterator():
        if guest.first_name:
            continue
        parts = (guest.name or "").strip().split(None, 1)
        guest.first_name = parts[0] if parts else ""
        guest.last_name = parts[1] if len(parts) > 1 else ""
        guest.save(update_fields=["first_name", "last_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0001_initial"),
        ("reservations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="legacy_id",
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="booking_status",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="reservation",
            name="booker_country",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AddField(
            model_name="reservation",
            name="booker_address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="import_source",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="reservation",
            name="booked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="units_count",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="persons_count",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="adults_count",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="children_count",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="children_ages",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="reservation",
            name="commission_percent",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="commission_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="payment_status",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="reservation",
            name="payment_provider",
            field=models.CharField(max_length=255, blank=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="travel_purpose",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="reservation",
            name="booking_device",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="reservation",
            name="nights_count",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="canceled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="details_pending",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="reservation",
            name="imported_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="reservation",
            name="booker_phone",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AlterField(
            model_name="reservation",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("expected", "Expected"),
                    ("checked_in", "Checked in"),
                    ("checked_out", "Checked out"),
                    ("canceled", "Canceled"),
                ],
                default="expected",
                max_length=32,
            ),
        ),
        migrations.RunPython(map_booking_status_to_operational, migrations.RunPython.noop),
        migrations.AddField(
            model_name="guest",
            name="legacy_id",
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="guest",
            name="first_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="guest",
            name="last_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(split_guest_names, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="guest",
            name="first_name",
            field=models.CharField(max_length=100),
        ),
        migrations.AddField(
            model_name="guest",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="guest",
            name="document_number",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="guest",
            name="nationality",
            field=models.CharField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name="guest",
            name="sex",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="guest",
            name="address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="guest",
            name="date_of_issue",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="guest",
            name="date_of_expiry",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="guest",
            name="issuing_authority",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="guest",
            name="personal_id_number",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="guest",
            name="document_additional_number",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="guest",
            name="additional_personal_id_number",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="guest",
            name="document_code",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="guest",
            name="document_type",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="guest",
            name="document_country",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="guest",
            name="document_country_iso2",
            field=models.CharField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name="guest",
            name="document_country_iso3",
            field=models.CharField(blank=True, max_length=3),
        ),
        migrations.AddField(
            model_name="guest",
            name="document_country_numeric",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AddField(
            model_name="guest",
            name="mrz_raw_text",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="guest",
            name="mrz_verified",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="guest",
            name="is_primary",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="guest",
            name="evisitor_status",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="guest",
            name="evisitor_registration_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="guest",
            options={"ordering": ["reservation_id", "-is_primary", "last_name", "first_name"]},
        ),
        migrations.CreateModel(
            name="ReservationUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("legacy_id", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("room_name", models.CharField(max_length=256)),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="units",
                        to="reservations.reservation",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant"),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reservation_units",
                        to="properties.unit",
                    ),
                ),
            ],
            options={
                "ordering": ["reservation_id", "sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="EvisitorSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("legacy_id", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("registration_id", models.UUIDField()),
                ("status", models.CharField(max_length=16)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("error_user_message", models.TextField(blank=True)),
                ("error_system_message", models.TextField(blank=True)),
                ("request_payload", models.JSONField(blank=True, default=dict)),
                ("response_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField()),
                (
                    "guest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="evisitor_submissions",
                        to="reservations.guest",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant"),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="reservation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_id__gt", "")),
                fields=("tenant", "external_id"),
                name="reservations_reservation_unique_tenant_external_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="reservation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("legacy_id__isnull", False)),
                fields=("tenant", "legacy_id"),
                name="reservations_reservation_unique_tenant_legacy_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="guest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_primary", True)),
                fields=("reservation",),
                name="reservations_guest_unique_primary_per_reservation",
            ),
        ),
        migrations.AddConstraint(
            model_name="guest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("legacy_id__isnull", False)),
                fields=("tenant", "legacy_id"),
                name="reservations_guest_unique_tenant_legacy_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="reservationunit",
            constraint=models.UniqueConstraint(
                fields=("reservation", "sort_order"),
                name="reservations_unit_unique_sort_order_per_reservation",
            ),
        ),
        migrations.AddConstraint(
            model_name="reservationunit",
            constraint=models.UniqueConstraint(
                condition=models.Q(("legacy_id__isnull", False)),
                fields=("tenant", "legacy_id"),
                name="reservations_unit_unique_tenant_legacy_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="evisitorsubmission",
            constraint=models.UniqueConstraint(
                condition=models.Q(("legacy_id__isnull", False)),
                fields=("tenant", "legacy_id"),
                name="reservations_evisitor_unique_tenant_legacy_id",
            ),
        ),
    ]
