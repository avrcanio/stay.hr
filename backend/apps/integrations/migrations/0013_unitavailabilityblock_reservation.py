from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0012_unitavailabilityblock"),
        ("reservations", "0007_reservation_channel_timestamps"),
    ]

    operations = [
        migrations.AddField(
            model_name="unitavailabilityblock",
            name="reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="smoobu_blocks",
                to="reservations.reservation",
            ),
        ),
    ]
