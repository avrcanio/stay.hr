import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0015_reservation_whatsapp_welcome_sent_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsAppDocumentBatchSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("wa_id", models.CharField(max_length=32)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("collecting", "Collecting"),
                            ("awaiting_confirm", "Awaiting confirm"),
                            ("after_no", "After no"),
                            ("processing", "Processing"),
                            ("done", "Done"),
                        ],
                        default="collecting",
                        max_length=20,
                    ),
                ),
                ("last_media_at", models.DateTimeField(blank=True, null=True)),
                ("prompt_sent_at", models.DateTimeField(blank=True, null=True)),
                ("prompt_count", models.PositiveSmallIntegerField(default=0)),
                ("after_no_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="whatsapp_batch_sessions",
                        to="reservations.documentintakejob",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="whatsapp_document_batch_sessions",
                        to="reservations.reservation",
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
            ],
            options={
                "ordering": ["-created_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="whatsappdocumentbatchsession",
            index=models.Index(fields=["reservation", "status"], name="reservations_reserva_8a4f2d_idx"),
        ),
    ]
