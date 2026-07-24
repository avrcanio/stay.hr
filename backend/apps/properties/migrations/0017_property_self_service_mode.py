from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0016_merge_property_0015_leaves"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="self_service_mode",
            field=models.CharField(
                choices=[
                    ("off", "Off"),
                    ("always", "Always"),
                    ("schedule", "Weekly schedule"),
                    ("calendar", "Calendar dates"),
                ],
                default="off",
                help_text=(
                    "When the guest-portal key guide card is shown: "
                    "off, always, weekday schedule, or explicit calendar dates."
                ),
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="self_service_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    'Schedule: {"weekdays": [1]} (Python weekday, Tuesday=1). '
                    'Calendar: {"dates": ["YYYY-MM-DD", ...]}.'
                ),
            ),
        ),
    ]
