from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0022_reservation_autocheckin_deadline_session_lost"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappdocumentbatchsession",
            name="confirm_interrupted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
