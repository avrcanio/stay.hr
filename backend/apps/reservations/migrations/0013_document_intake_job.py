import django.db.models.deletion
from django.db import migrations, models

import apps.reservations.models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
        ("reservations", "0012_reservation_status_no_show"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentIntakeJob",
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
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("processing", "Processing"),
                            ("done", "Done"),
                            ("failed", "Failed"),
                            ("applied", "Applied"),
                        ],
                        default="queued",
                        max_length=16,
                    ),
                ),
                ("device_id", models.CharField(blank=True, default="", max_length=128)),
                ("ocr_result", models.JSONField(blank=True, default=dict)),
                ("matches", models.JSONField(blank=True, default=list)),
                ("applied_result", models.JSONField(blank=True, default=list)),
                ("error_message", models.TextField(blank=True, default="")),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)ss",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="DocumentIntakeImage",
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
                (
                    "image",
                    models.ImageField(
                        upload_to=apps.reservations.models.document_intake_image_upload_to,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("detected_side", models.CharField(blank=True, default="", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="reservations.documentintakejob",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)ss",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
    ]
