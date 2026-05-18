import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0001_initial"),
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrationconfig",
            name="property",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="integration_configs",
                to="properties.property",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="integrationconfig",
            name="integrations_config_unique_tenant_provider",
        ),
        migrations.AddConstraint(
            model_name="integrationconfig",
            constraint=models.UniqueConstraint(
                fields=("tenant", "provider", "property"),
                name="integrations_config_unique_tenant_provider_property",
            ),
        ),
    ]
