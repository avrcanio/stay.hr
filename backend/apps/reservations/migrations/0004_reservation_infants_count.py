from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0003_id_document_scan_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="infants_count",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
