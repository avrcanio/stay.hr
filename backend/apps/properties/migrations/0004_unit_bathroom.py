import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0003_unit_bed"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UnitBathroom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_private", models.BooleanField(default=True)),
                ("is_inside_room", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bathrooms", to="properties.unit")),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="unitbathroom",
            constraint=models.UniqueConstraint(fields=("unit", "sort_order"), name="properties_unitbathroom_unique_unit_sort_order"),
        ),
    ]
