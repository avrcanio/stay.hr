from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0013_unitavailabilityblock_reservation"),
        ("reservations", "0007_reservation_channel_timestamps"),
    ]

    operations = [
        migrations.AlterField(
            model_name="integrationconfig",
            name="provider",
            field=models.CharField(
                choices=[
                    ("booking", "Booking"),
                    ("email", "Email"),
                    ("ical", "iCal"),
                    ("evisitor", "eVisitor"),
                    ("channex", "Channex"),
                    ("smoobu", "Smoobu"),
                    ("whatsapp", "WhatsApp"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="routing_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Meta phone_number_id for WhatsApp tenant routing.",
                max_length=64,
            ),
        ),
        migrations.AddConstraint(
            model_name="integrationconfig",
            constraint=models.UniqueConstraint(
                condition=models.Q(("routing_key__gt", "")),
                fields=("provider", "routing_key"),
                name="integrations_config_unique_provider_routing_key",
            ),
        ),
        migrations.CreateModel(
            name="WhatsAppMessage",
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
                ("wamid", models.CharField(max_length=128, unique=True)),
                ("wa_id", models.CharField(db_index=True, max_length=32)),
                ("phone_number_id", models.CharField(blank=True, max_length=32)),
                (
                    "direction",
                    models.CharField(
                        choices=[("inbound", "Inbound"), ("outbound", "Outbound")],
                        max_length=16,
                    ),
                ),
                ("message_type", models.CharField(blank=True, max_length=32)),
                ("body", models.TextField(blank=True)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "integration",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="whatsapp_messages",
                        to="integrations.integrationconfig",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="whatsapp_messages",
                        to="reservations.reservation",
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
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="whatsappmessage",
            index=models.Index(
                fields=["tenant", "wa_id", "created_at"],
                name="integration_tenant__wa_msg_idx",
            ),
        ),
    ]
