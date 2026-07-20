from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0004_invoice_buyer_country"),
    ]

    operations = [
        migrations.AddField(
            model_name="fiscalizationattempt",
            name="fiskal_request_id",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
