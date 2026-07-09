# Generated manually for guest_checkin_opens_days_before

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0013_property_financial_report_recipients"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="guest_checkin_opens_days_before",
            field=models.PositiveSmallIntegerField(
                default=7,
                help_text=(
                    "Days before arrival when guest web check-in opens "
                    "(session opens_at, wizard link validity)."
                ),
            ),
        ),
    ]
