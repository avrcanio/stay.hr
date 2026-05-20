import apps.reservations.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0003_id_document_scan_log"),
    ]

    operations = [
        migrations.CreateModel(
            name="IdRecognitionSample",
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
                        upload_to=apps.reservations.models.id_recognition_sample_upload_to
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("mrz_plus", "MRZ Plus"),
                            ("mrz_legacy", "MRZ Legacy"),
                        ],
                        default="mrz_plus",
                        max_length=32,
                    ),
                ),
                ("document_type", models.CharField(blank=True, default="", max_length=32)),
                ("raw_mrz", models.TextField(blank=True, default="")),
                ("ocr_text", models.TextField(blank=True, default="")),
                ("device_id", models.CharField(blank=True, default="", max_length=128)),
                ("parsed_snapshot", models.JSONField(blank=True, default=dict)),
                ("content_sha256", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "guest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="id_recognition_samples",
                        to="reservations.guest",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="id_recognition_samples",
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
