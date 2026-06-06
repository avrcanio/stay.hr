from django.db import migrations, models

import apps.integrations.models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0023_whatsappmessage_media_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="channexmessage",
            name="media_file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.integrations.models.channex_message_media_upload_to,
            ),
        ),
    ]
