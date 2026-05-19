import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0003_id_document_scan_log"),
        ("tenants", "0001_initial"),
        ("integrations", "0005_integrationconfig_channex_provider"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChannexBookingRevision",
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
                ("revision_id", models.CharField(max_length=36, unique=True)),
                ("booking_id", models.CharField(db_index=True, max_length=36)),
                ("channex_status", models.CharField(blank=True, max_length=32)),
                ("acknowledged_at", models.DateTimeField(auto_now_add=True)),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="channex_revisions",
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
                "ordering": ["-acknowledged_at"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "booking_id"],
                        name="integrations_channex_tenant_booking_idx",
                    )
                ],
            },
        ),
    ]
