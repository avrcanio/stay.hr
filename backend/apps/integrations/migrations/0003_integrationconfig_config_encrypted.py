from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0002_integration_property_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrationconfig",
            name="config_encrypted",
            field=models.TextField(blank=True, default=""),
        ),
    ]
