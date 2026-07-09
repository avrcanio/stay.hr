import apps.reservations.booking_payout_models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0015_merge_key_handover_and_financial_report"),
        ("reservations", "0027_guestcheckinsession_ready_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingPayoutImport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("payout_id", models.CharField(db_index=True, max_length=64)),
                ("payout_date", models.DateField()),
                ("currency", models.CharField(max_length=3)),
                (
                    "source_file",
                    models.FileField(
                        upload_to=apps.reservations.booking_payout_models.booking_payout_import_upload_to
                    ),
                ),
                ("source_sha256", models.CharField(blank=True, max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("parsed", "Parsed"),
                            ("applied", "Applied"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("applied_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("summary_snapshot", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "applied_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="booking_payout_applies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "property_obj",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="booking_payout_imports",
                        to="properties.property",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_set",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="booking_payout_uploads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="BookingPayoutLine",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("line_number", models.PositiveIntegerField()),
                ("booking_number", models.CharField(db_index=True, max_length=64)),
                ("guest_name", models.CharField(blank=True, max_length=255)),
                ("check_in", models.DateField()),
                ("check_out", models.DateField()),
                ("gross_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("commission_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "service_fee",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                ("net_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(max_length=3)),
                ("reservation_status", models.CharField(blank=True, max_length=32)),
                (
                    "match_status",
                    models.CharField(
                        choices=[
                            ("matched", "Matched"),
                            ("unmatched", "Unmatched"),
                            ("duplicate", "Duplicate"),
                        ],
                        default="unmatched",
                        max_length=16,
                    ),
                ),
                ("source_row", models.JSONField(default=dict)),
                ("warnings", models.JSONField(blank=True, default=dict)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                (
                    "import_batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="reservations.bookingpayoutimport",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="booking_payout_lines",
                        to="reservations.reservation",
                    ),
                ),
            ],
            options={
                "ordering": ["line_number"],
            },
        ),
        migrations.AddField(
            model_name="reservation",
            name="booking_payout_id",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="reservation",
            name="booking_payout_net",
            field=models.DecimalField(decimal_places=2, max_digits=12, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="booking_payout_received_at",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="booking_payout_service_fee",
            field=models.DecimalField(decimal_places=2, max_digits=12, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="booking_payout_line",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="applied_reservations",
                to="reservations.bookingpayoutline",
            ),
        ),
        migrations.AddConstraint(
            model_name="bookingpayoutimport",
            constraint=models.UniqueConstraint(
                fields=("property_obj", "payout_id"),
                name="reservations_bookingpayoutimport_unique_property_payout",
            ),
        ),
        migrations.AddConstraint(
            model_name="bookingpayoutline",
            constraint=models.UniqueConstraint(
                fields=("import_batch", "line_number"),
                name="reservations_bookingpayoutline_unique_import_line",
            ),
        ),
    ]
