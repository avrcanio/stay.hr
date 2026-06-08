from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0017_whatsapp_operator_session"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="whatsapp_autocheckin_intro_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="whatsapp_autocheckin_engaged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="WhatsAppGuestAutocheckinSession",
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
                ("wa_id", models.CharField(max_length=32)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("awaiting_booking_code", "Awaiting booking code"),
                        ],
                        default="awaiting_booking_code",
                        max_length=24,
                    ),
                ),
                ("last_activity_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["-last_activity_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "wa_id", "status"],
                        name="reservation_wa_guest_ac_si_tenant_wa_st_idx",
                    )
                ],
            },
        ),
    ]
