from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0009_property_whatsapp_autocheckin_email_lead"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="guest_info",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Guest FAQ, localized WhatsApp/check-in texts, maps link, entrance image path.",
            ),
        ),
    ]
