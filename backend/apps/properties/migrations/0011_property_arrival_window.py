from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0010_property_guest_info"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="after_hours_arrival_policy",
            field=models.CharField(
                choices=[
                    ("contact", "Contact phone"),
                    ("not_allowed", "Entry not allowed after latest time"),
                ],
                default="contact",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="after_hours_contact_phone",
            field=models.CharField(
                blank=True,
                help_text="Phone for late arrivals outside the window. Falls back to property.contact.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="check_in_latest_time",
            field=models.TimeField(
                blank=True,
                help_text="Latest self-service arrival time (property local). Null = no upper bound.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="guest_arrival_auto_reply_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Auto-reply on guest arrival-time messages (WhatsApp, email, Channex).",
            ),
        ),
    ]
