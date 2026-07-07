from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0023_whatsapp_document_batch_confirm_interrupted"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReservationVersion",
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
                    "scope",
                    models.CharField(
                        choices=[
                            ("messages", "Messages"),
                            ("payments", "Payments"),
                            ("documents", "Documents"),
                            ("checkin", "Check-in"),
                            ("housekeeping", "Housekeeping"),
                        ],
                        max_length=32,
                    ),
                ),
                ("version", models.PositiveBigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="version_rows",
                        to="reservations.reservation",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["reservation", "scope"],
                        name="reservations_reservat_0a8f0d_idx",
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="reservationversion",
            constraint=models.UniqueConstraint(
                fields=("reservation", "scope"),
                name="reservation_scope_unique",
            ),
        ),
    ]
