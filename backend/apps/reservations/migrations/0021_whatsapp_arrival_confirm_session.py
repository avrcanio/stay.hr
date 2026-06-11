from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0020_operator_session_status_max_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="guest_stated_arrival_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="guest_stated_arrival_text",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.CreateModel(
            name="WhatsAppArrivalConfirmSession",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("awaiting_arrived", "Awaiting arrived"),
                            ("awaiting_time", "Awaiting time"),
                            ("done", "Done"),
                            ("declined", "Declined"),
                        ],
                        default="awaiting_arrived",
                        max_length=20,
                    ),
                ),
                (
                    "trigger",
                    models.CharField(
                        choices=[
                            ("guest_deadline_plus_30", "Guest deadline +30"),
                            ("nightly_23h", "Nightly 23h"),
                        ],
                        max_length=24,
                    ),
                ),
                ("guest_stated_arrival_text", models.CharField(blank=True, max_length=255)),
                ("guest_stated_arrival_at", models.DateTimeField(blank=True, null=True)),
                ("prompted_at", models.DateTimeField(blank=True, null=True)),
                ("responded_operator_wa_id", models.CharField(blank=True, max_length=32)),
                ("confirmed_arrival_at", models.DateTimeField(blank=True, null=True)),
                ("celery_task_id", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="whatsapp_arrival_confirm_sessions",
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
        migrations.AddIndex(
            model_name="whatsapparrivalconfirmsession",
            index=models.Index(
                fields=["reservation", "status"],
                name="reservations_whatsapp_arrival_res_status_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="whatsapparrivalconfirmsession",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("status__in", ("awaiting_arrived", "awaiting_time"))
                ),
                fields=("reservation",),
                name="reservations_arrival_confirm_one_active_per_reservation",
            ),
        ),
    ]
