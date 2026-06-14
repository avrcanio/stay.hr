# Generated manually for WhatsApp autocheckin deadline tracking

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0021_whatsapp_arrival_confirm_session"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="whatsapp_autocheckin_docs_deadline_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Scheduled Celery ETA for docs deadline (check_in_time + 30 min).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="reservation",
            name="whatsapp_autocheckin_session_lost",
            field=models.BooleanField(
                default=False,
                help_text="Welcome template sent but guest never engaged before check_in_time - 1h.",
            ),
        ),
    ]
