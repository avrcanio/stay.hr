from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0008_property_whatsapp_autocheckin"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="whatsapp_autocheckin_email_lead_minutes",
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text="Intro email this many minutes before whatsapp_autocheckin_time (same day).",
            ),
        ),
    ]
