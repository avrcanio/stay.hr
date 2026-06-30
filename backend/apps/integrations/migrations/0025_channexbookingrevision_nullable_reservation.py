import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0024_channexmessage_media_file"),
        ("reservations", "0003_id_document_scan_log"),
    ]

    operations = [
        migrations.AlterField(
            model_name="channexbookingrevision",
            name="reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="channex_revisions",
                to="reservations.reservation",
            ),
        ),
    ]
