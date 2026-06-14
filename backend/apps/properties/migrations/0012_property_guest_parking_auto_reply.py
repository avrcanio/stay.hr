from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0011_property_arrival_window"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="guest_parking_auto_reply_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Auto-reply when guest asks about parking (WhatsApp, email, Channex).",
            ),
        ),
    ]
