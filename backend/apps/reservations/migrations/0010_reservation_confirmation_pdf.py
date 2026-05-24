from django.db import migrations, models

import apps.reservations.models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0009_reservation_status_refused"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="confirmation_pdf",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.reservations.models.booking_confirmation_pdf_upload_to,
            ),
        ),
    ]
