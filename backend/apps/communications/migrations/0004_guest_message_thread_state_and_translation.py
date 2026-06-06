from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0003_guestmessagechannel_booking"),
    ]

    operations = [
        migrations.CreateModel(
            name="GuestMessageThreadState",
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
                ("reply_dismissed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "reservation",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_message_thread_state",
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
                "verbose_name": "Guest message thread state",
                "verbose_name_plural": "Guest message thread states",
            },
        ),
        migrations.CreateModel(
            name="GuestMessageTranslation",
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
                    "message_source",
                    models.CharField(
                        choices=[
                            ("whatsapp", "WhatsApp"),
                            ("outbound", "Outbound"),
                            ("booking", "Booking.com"),
                        ],
                        max_length=16,
                    ),
                ),
                ("source_id", models.PositiveIntegerField()),
                ("target_lang", models.CharField(max_length=8)),
                ("translated_text", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Guest message translation",
                "verbose_name_plural": "Guest message translations",
            },
        ),
        migrations.AddIndex(
            model_name="guestmessagethreadstate",
            index=models.Index(
                fields=["tenant", "reservation"],
                name="communicati_tenant__a8b2c1_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="guestmessagetranslation",
            index=models.Index(
                fields=["tenant", "message_source", "source_id"],
                name="communicati_tenant__d4e5f6_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="guestmessagetranslation",
            constraint=models.UniqueConstraint(
                fields=("tenant", "message_source", "source_id", "target_lang"),
                name="guestmessagetranslation_unique_cache",
            ),
        ),
    ]
