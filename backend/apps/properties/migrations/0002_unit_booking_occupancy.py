from django.db import migrations, models


def backfill_unit_capacity(apps, schema_editor):
    Unit = apps.get_model("properties", "Unit")
    for unit in Unit.objects.all().iterator():
        max_guests = max(unit.capacity_adults + unit.capacity_children, 1)
        unit.capacity_max_guests = max_guests
        unit.capacity_infants = 0
        unit.save(update_fields=["capacity_max_guests", "capacity_infants"])


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="capacity_max_guests",
            field=models.PositiveSmallIntegerField(default=2),
        ),
        migrations.AddField(
            model_name="unit",
            name="capacity_infants",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(backfill_unit_capacity, migrations.RunPython.noop),
    ]
