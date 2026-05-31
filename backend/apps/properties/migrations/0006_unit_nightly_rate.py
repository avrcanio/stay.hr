from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0005_property_tourist_tax_category_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="default_nightly_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="unit",
            name="nightly_rate_currency",
            field=models.CharField(default="EUR", max_length=3),
        ),
    ]
