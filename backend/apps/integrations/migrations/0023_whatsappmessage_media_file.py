from django.db import migrations, models

import apps.integrations.models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0022_channexreview_content_translations"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappmessage",
            name="media_file",
            field=models.FileField(
                blank=True,
                default="",
                upload_to=apps.integrations.models.whatsapp_outbound_media_upload_to,
            ),
        ),
    ]
