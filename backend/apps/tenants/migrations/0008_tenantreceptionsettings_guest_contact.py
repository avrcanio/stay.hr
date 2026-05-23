from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0007_staffprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantreceptionsettings",
            name="guest_contact_email",
            field=models.EmailField(
                blank=True,
                help_text="From/Reply-To address for guest booking confirmation and refusal emails.",
                max_length=254,
            ),
        ),
        migrations.AddField(
            model_name="tenantreceptionsettings",
            name="guest_contact_name",
            field=models.CharField(
                blank=True,
                help_text="Display name for guest emails (e.g. property name).",
                max_length=255,
            ),
        ),
    ]
