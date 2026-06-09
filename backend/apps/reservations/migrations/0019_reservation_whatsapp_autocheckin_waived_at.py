from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0018_reservation_autocheckin_intro_engaged"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="whatsapp_autocheckin_waived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
