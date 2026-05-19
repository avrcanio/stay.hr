from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0003_tenantmembership"),
    ]

    operations = [
        migrations.AddField(
            model_name="apiapplication",
            name="fcm_token",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="apiapplication",
            name="fcm_token_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
