# Generated manually for GuestCheckInSession

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0024_reservationversion"),
    ]

    operations = [
        migrations.CreateModel(
            name="GuestCheckInSession",
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
                    "token",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("completed", "Completed"),
                            ("expired", "Expired"),
                            ("revoked", "Revoked"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("opens_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_from",
                    models.CharField(
                        choices=[
                            ("email", "Email"),
                            ("whatsapp_autocheckin", "WhatsApp autocheck-in"),
                            ("channex", "Channex"),
                            ("reception_manual", "Reception manual"),
                        ],
                        max_length=32,
                    ),
                ),
                ("last_activity_at", models.DateTimeField(auto_now=True)),
                ("wa_id", models.CharField(blank=True, max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_checkin_sessions",
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
            model_name="guestcheckinsession",
            index=models.Index(
                fields=["reservation", "status"],
                name="reservations_guest_checkin_res_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="guestcheckinsession",
            index=models.Index(
                fields=["token"],
                name="reservations_guest_checkin_token_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="guestcheckinsession",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "active")),
                fields=("reservation",),
                name="reservations_guest_checkin_one_active_per_reservation",
            ),
        ),
    ]
