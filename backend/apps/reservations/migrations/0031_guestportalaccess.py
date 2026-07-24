# Generated manually for GuestPortalAccess

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0030_merge_booking_payout_leaves"),
    ]

    operations = [
        migrations.CreateModel(
            name="GuestPortalAccess",
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
                            ("revoked", "Revoked"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("opens_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                (
                    "created_from",
                    models.CharField(
                        choices=[
                            ("whatsapp", "WhatsApp"),
                            ("email", "Email"),
                            ("reception_manual", "Reception manual"),
                            ("system", "System"),
                        ],
                        max_length=32,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_portal_accesses",
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
            model_name="guestportalaccess",
            index=models.Index(
                fields=["reservation", "status"],
                name="reservation_reserva_6f2a1c_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="guestportalaccess",
            index=models.Index(fields=["token"], name="reservation_token_c8e4d1_idx"),
        ),
        migrations.AddConstraint(
            model_name="guestportalaccess",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "active")),
                fields=("reservation",),
                name="reservations_guest_portal_one_active_per_reservation",
            ),
        ),
    ]
