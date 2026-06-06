from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0015_whatsapp_index_fix"),
        ("reservations", "0013_document_intake_job"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentintakejob",
            name="reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="document_intake_jobs",
                to="reservations.reservation",
            ),
        ),
        migrations.AddField(
            model_name="documentintakejob",
            name="source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("hospira_batch", "Hospira batch"),
                    ("whatsapp", "WhatsApp"),
                ],
                default="",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="documentintakejob",
            name="whatsapp_message",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="document_intake_jobs",
                to="integrations.whatsappmessage",
            ),
        ),
        migrations.AddField(
            model_name="documentintakejob",
            name="whatsapp_reply_sent",
            field=models.BooleanField(default=False),
        ),
    ]
