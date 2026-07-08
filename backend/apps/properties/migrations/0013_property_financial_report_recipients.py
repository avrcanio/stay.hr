from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0012_property_guest_parking_auto_reply"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="financial_report_recipients",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Comma-separated emails for monthly property financial report (check-out period).",
            ),
        ),
    ]
