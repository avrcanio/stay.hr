import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0001_initial"),
        ("integrations", "0009_integrationconfig_smoobu_provider"),
    ]

    operations = [
        migrations.CreateModel(
            name="UnitRateDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("rate", models.DecimalField(decimal_places=2, max_digits=10)),
                ("min_stay", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("smoobu_synced_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant"),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rate_days",
                        to="properties.unit",
                    ),
                ),
            ],
            options={
                "ordering": ["date", "unit_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="unitrateday",
            constraint=models.UniqueConstraint(
                fields=("tenant", "unit", "date"),
                name="integrations_unitrateday_unique_tenant_unit_date",
            ),
        ),
        migrations.AddIndex(
            model_name="unitrateday",
            index=models.Index(
                fields=["tenant", "unit", "smoobu_synced_at"],
                name="integration_tenant__d7e8f9_idx",
            ),
        ),
    ]
