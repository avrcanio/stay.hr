from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0005_guest_inbound_message"),
        ("reservations", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GuestInboundMessage",
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
                    "channel",
                    models.CharField(
                        choices=[
                            ("email", "Email"),
                            ("whatsapp", "WhatsApp"),
                            ("booking", "Booking.com"),
                        ],
                        max_length=16,
                    ),
                ),
                ("body_text", models.TextField()),
                ("from_email", models.EmailField(blank=True, default="", max_length=254)),
                ("subject", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_inbound_messages",
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
                "verbose_name": "Guest inbound message",
                "verbose_name_plural": "Guest inbound messages",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="guestinboundmessage",
            index=models.Index(
                fields=["tenant", "reservation", "created_at"],
                name="communicati_tenant__inbound_idx",
            ),
        ),
    ]
