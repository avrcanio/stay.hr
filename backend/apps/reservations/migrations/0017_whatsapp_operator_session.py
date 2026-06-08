from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0016_whatsapp_document_batch_session"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentintakejob",
            name="source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("hospira_batch", "Hospira batch"),
                    ("whatsapp", "WhatsApp"),
                    ("whatsapp_operator", "WhatsApp operator"),
                ],
                default="",
                max_length=32,
            ),
        ),
        migrations.CreateModel(
            name="WhatsAppOperatorSession",
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
                ("operator_wa_id", models.CharField(max_length=32)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("collecting", "Collecting"),
                            ("processing", "Processing"),
                            ("done", "Done"),
                            ("failed", "Failed"),
                        ],
                        default="collecting",
                        max_length=16,
                    ),
                ),
                ("last_activity_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="whatsapp_operator_sessions",
                        to="reservations.documentintakejob",
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
                "ordering": ["-last_activity_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "operator_wa_id", "status"],
                        name="reservation_wa_op_sess_tenant_wa_st_idx",
                    )
                ],
            },
        ),
    ]
