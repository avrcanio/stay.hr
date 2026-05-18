import django.db.models.deletion
from django.db import migrations, models

import apps.reservations.models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
        ("reservations", "0002_uzorita_reception_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="IdDocument",
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
                ("image_path", models.CharField(blank=True, default="", max_length=500)),
                (
                    "face_photo",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=apps.reservations.models.id_document_face_upload_to,
                    ),
                ),
                (
                    "signature_photo",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=apps.reservations.models.id_document_signature_upload_to,
                    ),
                ),
                (
                    "front_photo",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=apps.reservations.models.id_document_front_upload_to,
                    ),
                ),
                (
                    "back_photo",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=apps.reservations.models.id_document_back_upload_to,
                    ),
                ),
                ("extracted_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "guest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="id_documents",
                        to="reservations.guest",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="DocumentScanLog",
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
                ("status", models.CharField(choices=[("ok", "OK"), ("failed", "Failed")], max_length=16)),
                ("method", models.CharField(blank=True, default="", max_length=8)),
                ("device_id", models.CharField(blank=True, default="", max_length=128)),
                ("scanned_at", models.DateTimeField(blank=True, null=True)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("suggested_fields", models.JSONField(blank=True, default=dict)),
                ("corrected_fields", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "guest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="document_scan_logs",
                        to="reservations.guest",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="document_scan_logs",
                        to="reservations.reservation",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "id"],
            },
        ),
    ]
