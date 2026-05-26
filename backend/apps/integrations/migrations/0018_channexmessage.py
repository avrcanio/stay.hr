from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0017_remove_smoobu"),
        ("reservations", "0007_reservation_channel_timestamps"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChannexMessage",
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
                ("channex_booking_id", models.CharField(db_index=True, max_length=64)),
                ("message_thread_id", models.CharField(blank=True, max_length=64)),
                ("channex_message_id", models.CharField(max_length=128, unique=True)),
                (
                    "direction",
                    models.CharField(
                        choices=[("inbound", "Inbound"), ("outbound", "Outbound")],
                        max_length=16,
                    ),
                ),
                (
                    "sender",
                    models.CharField(
                        choices=[("guest", "Guest"), ("property", "Property")],
                        max_length=16,
                    ),
                ),
                ("body", models.TextField(blank=True)),
                ("have_attachment", models.BooleanField(default=False)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "integration",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="channex_messages",
                        to="integrations.integrationconfig",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="channex_messages",
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
            model_name="channexmessage",
            index=models.Index(
                fields=["tenant", "reservation", "created_at"],
                name="integration_tenant__chn_msg_idx",
            ),
        ),
    ]
