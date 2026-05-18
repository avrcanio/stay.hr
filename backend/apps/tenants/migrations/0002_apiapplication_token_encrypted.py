from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="apiapplication",
            name="token_encrypted",
            field=models.TextField(blank=True, default=""),
        ),
    ]
