from datetime import time

from django.db import migrations, models


def backfill_property_check_times(apps, schema_editor):
    Property = apps.get_model("properties", "Property")
    Property.objects.update(
        check_in_time=time(15, 0),
        check_out_time=time(11, 0),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0006_unit_nightly_rate"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="check_in_time",
            field=models.TimeField(default=time(15, 0)),
        ),
        migrations.AddField(
            model_name="property",
            name="check_out_time",
            field=models.TimeField(default=time(11, 0)),
        ),
        migrations.RunPython(backfill_property_check_times, migrations.RunPython.noop),
    ]
