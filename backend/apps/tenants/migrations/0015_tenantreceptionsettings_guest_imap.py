from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0014_tenantreceptionsettings_whatsapp_operator_phones"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantreceptionsettings",
            name="guest_imap_last_uid",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Last processed IMAP UID for guest inbox polling (INBOX).",
            ),
        ),
        migrations.AddField(
            model_name="tenantreceptionsettings",
            name="guest_imap_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Poll guest_contact_email inbox for Booking.com guest replies.",
            ),
        ),
    ]
