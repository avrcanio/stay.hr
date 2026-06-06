from django.db import migrations, models

import apps.communications.models


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0006_guest_inbound_message"),
    ]

    operations = [
        migrations.AddField(
            model_name="guestoutboundmessage",
            name="media_file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.communications.models.guest_outbound_media_upload_to,
            ),
        ),
    ]
