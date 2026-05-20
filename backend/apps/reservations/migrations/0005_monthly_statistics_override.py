from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0004_reservation_infants_count"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MonthlyStatisticsOverride",
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
                ("year", models.PositiveSmallIntegerField()),
                (
                    "month",
                    models.PositiveSmallIntegerField(
                        validators=[
                            MinValueValidator(1),
                            MaxValueValidator(12),
                        ],
                    ),
                ),
                ("revenue", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "commission",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                    ),
                ),
                ("nights", models.PositiveIntegerField()),
                ("currency", models.CharField(default="EUR", max_length=3)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ručna statistika (mjesec)",
                "verbose_name_plural": "Ručna statistika (mjesec)",
                "ordering": ["-year", "-month"],
            },
        ),
        migrations.AddConstraint(
            model_name="monthlystatisticsoverride",
            constraint=models.UniqueConstraint(
                fields=("tenant", "year", "month"),
                name="reservations_monthly_stats_override_tenant_year_month_uniq",
            ),
        ),
    ]
