from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0011_rename_integration_tenant__a8f1c2_idx_integration_tenant__0e529e_idx_and_more"),
        ("properties", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UnitAvailabilityBlock",
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
                ("check_in", models.DateField()),
                ("check_out", models.DateField()),
                ("smoobu_booking_id", models.CharField(max_length=64)),
                (
                    "created_via",
                    models.CharField(
                        choices=[("hospira", "Hospira")],
                        default="hospira",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="tenants.tenant",
                    ),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="availability_blocks",
                        to="properties.unit",
                    ),
                ),
            ],
            options={
                "ordering": ["check_in", "unit_id"],
            },
        ),
        migrations.AddIndex(
            model_name="unitavailabilityblock",
            index=models.Index(
                fields=["tenant", "unit", "check_in"],
                name="integration_tenant__4b8e2a_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="unitavailabilityblock",
            constraint=models.UniqueConstraint(
                fields=("tenant", "smoobu_booking_id"),
                name="integrations_unitblock_unique_tenant_smoobu_id",
            ),
        ),
    ]
