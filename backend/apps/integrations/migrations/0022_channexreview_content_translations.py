from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0021_channexreview"),
    ]

    operations = [
        migrations.AddField(
            model_name="channexreview",
            name="content_translations",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
