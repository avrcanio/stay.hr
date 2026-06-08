from datetime import time

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0007_property_check_in_out_times"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="whatsapp_autocheckin_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="property",
            name="whatsapp_autocheckin_time",
            field=models.TimeField(default=time(8, 0)),
        ),
    ]
