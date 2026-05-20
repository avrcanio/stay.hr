import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0002_unit_booking_occupancy"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UnitBed",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bed_type", models.CharField(
                    choices=[
                        ("twin", "Twin bed(s) / 90-130 cm wide"),
                        ("full", "Full bed(s) / 131-150 cm wide"),
                        ("queen", "Queen bed(s) / 151-180 cm wide"),
                        ("king", "King bed(s) / 181-210 cm wide"),
                        ("bunk", "Bunk bed / Variable size"),
                        ("sofa", "Sofa bed / Variable size"),
                        ("futon", "Futon bed(s) / Variable size"),
                    ],
                    max_length=16,
                )),
                ("count", models.PositiveSmallIntegerField(default=1)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="beds", to="properties.unit")),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="unitbed",
            constraint=models.UniqueConstraint(fields=("unit", "bed_type"), name="properties_unitbed_unique_unit_bed_type"),
        ),
    ]
