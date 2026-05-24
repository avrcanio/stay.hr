from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0008_tenantreceptionsettings_guest_contact"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantreceptionsettings",
            name="guest_smtp_password_encrypted",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Encrypted SMTP password for guest_contact_email (mail.{domain}:587).",
            ),
        ),
    ]
