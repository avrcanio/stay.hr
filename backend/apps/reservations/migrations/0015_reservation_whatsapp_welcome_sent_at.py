from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0014_document_intake_whatsapp"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="whatsapp_welcome_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
